# Local verification output

The scripts in `scripts/uat-*` write results here. Generated reports and images
are intentionally ignored by Git: a real desktop run can include conversations,
account information, local paths or screen content. Never publish those outputs
without reviewing them. Use synthetic fixtures for bug reports.

Public verification scope and limitations are recorded in
[docs/testing.md](../docs/testing.md). GitHub Actions runs automated tests;
it does not certify the native desktop or access a user's ChatGPT account.
