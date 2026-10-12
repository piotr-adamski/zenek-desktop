# Contributing to Zenek

Read the [architecture](docs/architecture.md), [privacy model](docs/privacy.md)
and [testing scope](docs/testing.md) before changing behavior. Keep public
documentation and issue reports in English; the current product UI and default
persona are Polish. Small, focused pull requests are welcome.

Use issues for reproducible bugs and feature proposals. Report vulnerabilities
privately through [SECURITY.md](SECURITY.md). Follow the
[Code of Conduct](CODE_OF_CONDUCT.md). Use synthetic screen, archive and conversation
fixtures. Never include tokens, private screenshots, memory databases or runtime evidence.

## Development

Install the native dependencies listed in [installation](docs/installation.md).
Then, from the repository:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e '.[dev]'
bash scripts/validate.sh
```

These checks do not start the desktop companion or authenticate to OpenAI.
Native UAT scripts are opt-in and may manipulate the installed user service,
UI or screenshots. Read each script and [testing.md](docs/testing.md) first.

## Pull requests and licensing

Fork the repo, make a branch, explain the behavior changed and provide relevant
verification. Preserve independent model profiles, explicit OFF settings,
privacy boundaries and local data. Avoid new services, dependencies or approval
loops without a concrete need. Maintainers review changes before merging.

Contributions use Apache-2.0 on an inbound-equals-outbound basis; no CLA is used.
Every contributed commit must certify the [DCO 1.1](DCO.md) with your own real name
and an email you are authorized to use (a GitHub noreply address is fine):

```bash
git commit -s
```

Never sign on behalf of another contributor. Keep CI and installation changes
explicit in the PR. CI runs on untrusted fork code with read-only permissions
and no account credentials; maintainer review remains necessary.
