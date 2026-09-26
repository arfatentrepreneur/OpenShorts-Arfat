# DMCA block for upload-post.com terms

Applied on 29-aug-2026 to `upload-post-landing/src/pages/terms-of-use.astro`,
right after **4.8 Intermediary Status** and before the `<h2>` of section 5.
Kept here as the record of what went in and of why the email is what it is.

**The agent email is info@upload-post.com, in both companies' terms.**
17 U.S.C. 512(c)(2) requires each site to publish substantially the same agent
information that is on file with the Copyright Office, and one legal entity
files one designation, so the same address has to appear on openshorts.app too.
It was chosen because that is the inbox that gets read daily and because
Upload-Post is the larger exposure of the two. Everything hinges on somebody
reading it the same working day.

```astro
    <p class="text-gray-700 dark:text-slate-300 mb-6">
      <strong>4.9 DMCA Designated Agent (United States):</strong> For rightsholders in the United States, TONVI TECH SL has designated the following agent to receive notifications of claimed copyright infringement under 17 U.S.C. &sect; 512(c)(2): <strong>Copyright Agent, TONVI TECH SL, Calle Puerta del Mar 18, 5th Floor, 29005 M&aacute;laga, Spain</strong>, email <a href="mailto:info@upload-post.com?subject=DMCA%20Notification" class="text-blue-600 dark:text-blue-400 underline">info@upload-post.com</a>. That is the address on file with the U.S. Copyright Office for this company, which also operates openshorts.app. Section 4.7 remains available to rightsholders anywhere in the world.
    </p>
    <p class="text-gray-700 dark:text-slate-300 mb-6">
      <strong>4.10 Content of a DMCA Notification:</strong> A notification must be in writing and include: a physical or electronic signature of the owner of the exclusive right allegedly infringed, or of a person authorised to act on their behalf; identification of the copyrighted work claimed to have been infringed; identification of the material claimed to be infringing and information reasonably sufficient to let us locate it; your address, telephone number and email address; a statement that you have a good-faith belief that the use is not authorised by the copyright owner, its agent, or the law; and a statement, made under penalty of perjury, that the information in the notification is accurate and that you are the owner or are authorised to act on the owner's behalf. Notifications that omit these elements may not be effective to give us actual knowledge of the material.
    </p>
    <p class="text-gray-700 dark:text-slate-300 mb-6">
      <strong>4.11 Counter-Notification and Restoration:</strong> If we remove or disable access to your material and you believe this was the result of a mistake or a misidentification, you may send a counter-notification to the designated agent under 17 U.S.C. &sect; 512(g), including your signature, identification of the material and the location at which it appeared before removal, a statement under penalty of perjury that you have a good-faith belief that the material was removed or disabled as a result of mistake or misidentification, and your consent to the jurisdiction of the United States federal district court for the judicial district in which you reside or, if your address is outside the United States, of any judicial district in which we may be found. We will forward the counter-notification to the complaining party and may restore the material in 10 to 14 business days unless that party notifies us that it has filed an action seeking a court order to restrain the allegedly infringing activity.
    </p>
    <p class="text-gray-700 dark:text-slate-300 mb-6">
      <strong>4.12 Repeat Infringers and Misrepresentation:</strong> In accordance with 17 U.S.C. &sect; 512(i), we have adopted and reasonably implement a policy of terminating, in appropriate circumstances, the accounts of users who are repeat infringers. Under 17 U.S.C. &sect; 512(f), any person who knowingly materially misrepresents that material is infringing, or that material was removed or disabled by mistake or misidentification, may be liable for the damages that misrepresentation causes.
    </p>
```

Also bump `Last Updated` at the top and bottom of that page when this goes in;
the file states the date twice.

## What must match the registration

When the designation is filed at dmca.copyright.gov, these four have to be the
same as what is published above, or the publication does not do its job:

- Agent name: Copyright Agent
- Organisation: TONVI TECH SL
- Address: Calle Puerta del Mar 18, 5th Floor, 29005 Malaga, Spain
- Email: info@upload-post.com

Alternate names on the designation: OpenShorts, openshorts.app, Upload-Post,
upload-post.com. The phone number is still missing and the form requires it.
