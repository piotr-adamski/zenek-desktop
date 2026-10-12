# Privacy and data flow

## Local storage

Conversation, settings, notes, sources, self-model revisions and usage counters
live in SQLCipher. Database key, OAuth credentials, optional API key and Portal
restore grant use the system Keyring. No plaintext fallback exists.

Normal capture processes raw screenshots in RAM without durable image storage.
The temporary redacted preview clears when capture stops. Observation memory may
save derived notes in the encrypted DB. Explicit JSON exports and opt-in native
test reports are separate files that may contain private data; never commit them
or attach them to public issues without review.

## Network destinations

| Destination | Purpose / data |
| --- | --- |
| `auth.openai.com` | OAuth consent, token refresh and OIDC validation |
| `api.openai.com` | Model catalog and inference with selected conversation/memory/observation context |
| Public Wikipedia / MediaWiki | Optional sandboxed public queries/pages |
| PyPI, distribution mirrors, GitHub | Dependencies and source installation/updates |

Inference goes directly to OpenAI. OCR avoids unnecessary image inference, but
relevant OCR text can still enter model context. If graphics justify vision,
the redacted image is sent. Requests use `store: false`; that setting does not
prove that all provider logs/retention are disabled. Provider terms apply.

The project has no analytics, hosted account DB, telemetry or shared credential.
It does not use ChatGPT Desktop token storage or automatically access ChatGPT
conversation history. Archive import is explicit.

## Screen safeguards and limits

Observation starts OFF and requires Portal consent. Each snapshot uses fresh
session/window metadata, OCR and masking before vision. Banking, government/tax,
social-insurance, infrastructure and Vault contexts are high risk. Email, social
sites and ordinary terminals are lower risk; exposed credential patterns still
trigger masking/rejection.

OCR, risk classification and secret-pattern detection are heuristics and may miss
content. They do not guarantee removal of every secret. Review the masking preview
and turn observation OFF for screens you do not want processed. Source activity
stops on lock/suspend/UI loss; saved ON survives. Automatic return requires a safe
session and existing restore grant. Explicit OFF never resumes automatically.

## Other boundaries

The Bubblewrap broker has no HOME, Keyring or memory DB. Validated public HTTPS
GET only: local/private addresses, upload, authenticated sessions and state-changing
paths are rejected. DNS uses the host network. It is not a general browser.

The model has no OS execution tools. Your running desktop session, OS, Keyring
and session D-Bus remain trusted. Encryption at rest does not protect against a
compromised running user session. Report boundary defects via [SECURITY.md](../SECURITY.md).
