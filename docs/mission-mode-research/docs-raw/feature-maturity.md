# Feature Maturity

How Factory labels feature maturity, and how releases and versioning work.

Factory ships quickly, so some capabilities reach you before they are fully settled. A
small set of maturity tags tells you how stable a feature is and what to expect from it.
This page explains those tags and how our releases and versioning work.

## Maturity tags

A maturity tag appears next to a page title and in the navigation sidebar. Most features
are stable and carry no tag, so a tag is only present when a feature is still maturing or
on its way out.

<LifecycleTag tag="Private Preview" /> marks a feature with limited or invite-only access
that is already running in production. It is stable enough to rely on, though access and
surface area are still expanding.

<LifecycleTag tag="Deprecated" /> marks a feature that is being phased out. Avoid it for
new work and migrate to the recommended alternative when you can.

**Generally available** features carry no tag. They are stable, supported, and safe to
build on, and this is the default for everything in the docs unless a tag says otherwise.

<Note>
  Generally available is the absence of a tag, not a label. "GA", "Beta", "Public
  Preview", and "Research Preview" are intentionally not part of the vocabulary, so you
  will never see them as tags.
</Note>

## Releases and versioning

The **[Full Changelog](/changelog/release-notes)** lists every notable change across the
Factory App, Droid CLI, and other surfaces, newest first. Subscribe to it as a feed at
`/changelog/rss.xml`.

The Droid CLI is versioned, and changelog entries note the version a change shipped in
(for example, `v1.10.0`). The Factory App and other hosted surfaces ship continuously, so
their changes are dated rather than versioned.

<Tip>
  Watching for a capability to graduate? Follow the full changelog; a feature dropping its{' '}
  <LifecycleTag tag="Private Preview" /> tag is announced there.
</Tip>
