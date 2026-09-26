"""API-key token semantics (cloud/api_keys.py).

The raw ``osk_`` value is shown once and only its sha256 is stored, so the
format and hashing rules are load-bearing: a drifting prefix would break
``looks_like_key`` routing in cloud/auth.py, and a non-deterministic hash would
lock every issued key out of the resolver.
"""
from cloud.api_keys import KEY_PREFIX, generate_key, hash_key, looks_like_key


class TestKeyGeneration:
    def test_raw_key_carries_the_prefix(self):
        raw, _hash, _prefix = generate_key()
        assert raw.startswith(KEY_PREFIX)

    def test_hash_matches_rehashing_the_raw_value(self):
        raw, token_hash, _prefix = generate_key()
        assert hash_key(raw) == token_hash

    def test_display_prefix_is_a_prefix_of_the_raw_key(self):
        raw, _hash, prefix = generate_key()
        assert raw.startswith(prefix)
        # Long enough to tell keys apart, short enough to be useless to guess.
        assert len(prefix) < len(raw) / 3

    def test_keys_are_unique(self):
        assert generate_key()[0] != generate_key()[0]

    def test_raw_key_has_enough_entropy(self):
        raw, _hash, _prefix = generate_key()
        assert len(raw) >= len(KEY_PREFIX) + 40  # token_urlsafe(32) ≈ 43 chars


class TestLooksLikeKey:
    def test_accepts_generated_keys(self):
        assert looks_like_key(generate_key()[0])

    def test_rejects_jwts_and_junk(self):
        assert not looks_like_key("eyJhbGciOiJIUzI1NiJ9.e30.abc")
        assert not looks_like_key("")
        assert not looks_like_key(None)
        assert not looks_like_key(123)
