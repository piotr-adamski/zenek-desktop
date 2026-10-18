# Security policy

Security reports are accepted for the latest preview release and `main`.
Older preview builds should be updated before reproducing an issue. This is
experimental desktop software; no remediation deadline or security certification
is promised.

## Private reporting

Use [GitHub Private Vulnerability Reporting](https://github.com/piotr-adamski/zenek-desktop/security/advisories/new).
If unavailable, contact the maintainer at
[piotr.adamski@brillnet-app.com](mailto:piotr.adamski@brillnet-app.com)
with subject `[zenek-desktop security]`.

Include the affected version/commit, GNOME/distribution versions, reproduction
steps using synthetic data, impact and any proposed correction. Do not post
vulnerabilities in public issues or PRs. Do not send real access tokens,
screenshots of sensitive accounts, archives or encrypted memory/key material.

Relevant boundaries include OAuth/OIDC, Keyring and SQLCipher access, screen
redaction, the public-web sandbox, notebook confinement, model tool dispatch,
autonomous character/agenda records, archive import and the session D-Bus interface.
Character autonomy does not authorize code execution or access outside the
notebook. Private hobbies are visible to the owner and may enter inference;
notebook text is not encrypted at rest. See [autonomy.md](docs/autonomy.md).
See [privacy.md](docs/privacy.md) for the current guarantees and limitations.
