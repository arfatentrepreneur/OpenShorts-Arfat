# ops/

Operational scripts for OpenShorts Cloud. Nothing here runs automatically:
each file is installed and scheduled on the host that needs it.

## `pg_backup.sh` — encrypted PostgreSQL backups, 30-day retention

The only backup mechanism this project has ever had in version control. Art.
32.1.c GDPR requires being able to restore availability of personal data after
an incident, and the privacy policy now states that a deletion is gone from
every copy within 30 days — this script is what makes both sentences true.

### What it does

1. `pg_dump` the cloud database (plain SQL, `--no-owner --no-privileges`).
2. gzip and **encrypt** it, in the same pipeline, with `age` (recommended) or
   `gpg`. Only ciphertext ever touches the disk or the bucket. Without a
   recipient key configured the script exits with an error rather than writing a
   readable dump — a plaintext copy of `users` in an object store is the
   incident this file exists to prevent.
3. Upload to `s3://…` (works with Cloudflare R2 via `BACKUP_S3_ENDPOINT`) or
   `gs://…`.
4. Delete backups older than `RETENTION_DAYS` (default 30).

### Install

```bash
# On the database host (el servidor de la base de datos), as root:
apt-get install -y postgresql-client age awscli        # or gnupg instead of age
install -m 0750 ops/pg_backup.sh /opt/openshorts/ops/pg_backup.sh
```

Generate a key pair **on your laptop, not on the server** — the server only
ever needs the public half, which is the whole point:

```bash
age-keygen -o openshorts-backup.key      # keep this file in a password manager
grep 'public key' openshorts-backup.key  # -> age1... goes on the server
```

Then create `/etc/openshorts-backup.env` (mode `0600`):

```sh
DATABASE_URL="postgres://user:pass@127.0.0.1:5432/openshorts"
BACKUP_AGE_RECIPIENT="age1................................................"
BACKUP_DEST="s3://openshorts-backups/pg"
BACKUP_S3_ENDPOINT="https://<accountid>.r2.cloudflarestorage.com"
AWS_ACCESS_KEY_ID="..."          # an R2 token scoped to THIS bucket only
AWS_SECRET_ACCESS_KEY="..."
RETENTION_DAYS=30
```

Dry run first — it dumps and encrypts locally but uploads nothing:

```bash
set -a; . /etc/openshorts-backup.env; set +a
DRY_RUN=1 /opt/openshorts/ops/pg_backup.sh
```

Schedule it:

```cron
15 3 * * * set -a; . /etc/openshorts-backup.env; set +a; /opt/openshorts/ops/pg_backup.sh >> /var/log/openshorts-backup.log 2>&1
```

### Restore (do this once, before you need it)

```bash
aws s3 cp --endpoint-url "$BACKUP_S3_ENDPOINT" \
  s3://openshorts-backups/pg/openshorts-pg-20260904T031500Z.sql.gz.age .
age -d -i openshorts-backup.key openshorts-pg-*.sql.gz.age | gunzip \
  | psql "postgres://…/openshorts_restore_test"
psql "postgres://…/openshorts_restore_test" -c 'select count(*) from users;'
```

A backup nobody has restored is a hypothesis. Write down the date of the last
successful restore test somewhere a person will read.

### Things to keep true

- **The bucket is not public and not the same bucket as user clips.** Give the
  backup token write access to its own bucket and nothing else.
- **The private key is not on the server.** If it were, an attacker with the
  server has both the ciphertext and the key.
- **`RETENTION_DAYS` and the privacy policy move together.** The policy tells
  users a deletion disappears from backups within 30 days
  (`docs/compliance/retencion.md`, `dashboard/seo/legal.js` §5). Raising the
  retention without changing that text makes the policy false.
- **Object-lock / versioning on the bucket would defeat the retention.** If you
  enable it for ransomware protection, set the lock window to the same 30 days,
  not longer.
