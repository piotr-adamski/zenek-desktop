# Configuration

Open `zenek settings`. Saved preferences and operational status are shown
separately. Current product labels and default conversation language are Polish.

## Account and models

Choose **Continue with ChatGPT** and authorize in your system browser. Each new
account registers its own OAuth client via `dynamic_agent_client`, with name
`Zenek Desktop Companion` and a persistent opaque host UUID. Issued client ID
and credentials stay in Keyring; later sign-ins reuse that registration.
No project-wide client secret or partner API key is required for this local
open-source flow. Registration and plan consent are personal actions; publishing
the repo does not approve account access for anyone else.

Zenek requests identity and eligible inference permission, not your ChatGPT
conversation history. See the official
[registration documentation](https://developers.openai.com/siwc/token-sharing-open-source/sign-in).
Choose/test conversation, background and vision profiles independently from the
catalog offered to your account. READY requires a completed profile test.
The original tested conversation used `gpt-6.1-sol / medium`; model access varies
by account. Fresh installations have no selected model.

One active SIWC registration is stored. Reauthorization must match it; disconnect
before connecting a different account. The paid API adapter requires an explicit
separate choice and your own API key. It is never an automatic fallback.

## Observation and comments

- Observation starts OFF. Enable it in Settings or **Okresowe zrzuty ekranu** in
  the tray, then choose a monitor in the Portal.
- Interval **15–3600 seconds**, default **60**. Each session closes after its
  snapshot. A brief GNOME sharing indicator is expected during acquisition.
- OCR `eng+pol` runs first. Graphics threshold defaults to **40%**, configurable
  **10–90%**. Text-heavy scenes use OCR instead of image inference.
- Screen-comment priority: off/balanced/high. Variety may skip a screen topic:
  no consecutive screen comments and at most two of the last five.
- Saved ON survives pauses and resumes from an existing grant after fresh safe
  UI/session state. Explicit OFF stays OFF. Portal faults show a reason and
  **Wznów zrzuty**, preserving the preference without an automatic retry loop.
- Hidden capture requires a separate option. Observation-memory settings control
  durable derived notes; disabled storage still permits transient model context
  when observation is enabled. Review [privacy.md](privacy.md).

## Interruptions and memory

`hide` leaves Core running; `stop` ends it. Fresh autostart is OFF. Settings control
quiet mode, idle/fullscreen behavior, bubble duration, frequency and independent
inference/web limits. Rolling counters/cooldowns survive restarts; returning from
inactivity does not create a backlog of missed comments.

Import means explicitly choosing local ZIP/JSON/TXT/MD archives, reviewing the
preview and selecting threads. No filesystem watcher or account-history scan
is used. Corrections, scoped deletion and explicit JSON export are available;
exports may contain personal information.

## Simulated personality

**Osobowość** provides the base instruction/traits and proposed instruction changes
with diff, approve/reject, history and rollback. Personalize the default persona
for your name and language.

**Model siebie i historia rozwoju** shows nine categories with source references,
confidence and revision history. Four seed facets provide a creative starting
direction. Existing background reflections supply up to three updates per reply;
limits are 120 active facets and 16 per category. Sources are required and owner
corrections are preserved. The model influences context, but cannot grant itself
permissions or approve base-instruction changes. This is playful simulation;
long-term coherence remains experimental.

Public web research is a separate OFF-by-default MediaWiki option. It does not
log into email, social media or websites.
