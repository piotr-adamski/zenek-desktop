# Releasing Zenek

Maintainer procedure for complete-source GitHub previews. Current release:
**0.2.0**, extension metadata revision **2**. Publication is separate from updating
a running desktop. Publish only within the owner's authorized scope.

## Prepare

1. Review the difference from the previous tag and preserve unrelated local work.
2. Update `pyproject.toml`, `src/zenek_core/__init__.py` and the integer revision in
   `gnome-extension/zenek@brillnet/metadata.json`. Check the broker User-Agent too.
3. Update the README, changelog and guides for actual behavior. Keep historical
   test evidence distinct from release checks and list remaining gaps.
4. Run `PYTHONNOUSERSITE=1 bash scripts/validate.sh`, shell syntax checks and
   `.venv/bin/python -m build`. Use the isolated workspace UAT for changes there.
5. Inspect the exact staged source and distributions. Never stage `notebook/`,
   private `evidence/`, databases, credentials, generated modules or local exports.
   Scan staged contents and the public commit range with Gitleaks **8.30.1**, the
   version pinned in the secret-scan workflow. Fixture exceptions must be narrow.
6. Commit with DCO sign-off, preview a normal fast-forward push to public `main`,
   then push only that ref. Private local refs must never be mirrored or tagged.

For an unchanged area, an existing adequate test is enough; add or repeat checks
for a concrete changed behavior or unresolved failure. Do not run live-provider,
capture or owner-session UAT just to publish documentation.

## Publish and read back

Wait for **CI** and **Secret scan** on the exact commit to succeed before creating
the preview release. Keep workflows read-only and pinned to approved action SHAs.

Create a complete source archive from that commit, for example:

```bash
git archive --format=tar.gz --prefix=zenek-desktop-0.2.0/ \
  --output=/tmp/zenek-desktop-0.2.0-source.tar.gz HEAD
```

Inspect archive paths and generate `SHA256SUMS` next to it. Publish tag `v0.2.0`
against the verified commit with release notes, archive and checksum. Mark it
as a preview/prerelease. Notes must explain supported desktops, significant
behavior changes, update steps, checks and known limitations.

Read back the public tag target, release state and assets; download the actual
uploaded files and verify their checksum. Compare the public README/version with
the local commit. Record results in the private requirements matrix under ignored
`evidence/`; never publish private development reports as release evidence.

## Distribution scope

GitHub source is the supported route. A Python build validates packaging but its
wheel alone omits the GNOME extension and user-service integration. PyPI, Flatpak
and GNOME Extensions publication are separate work. The repository's community,
security, licensing and contribution files remain applicable to every preview.
