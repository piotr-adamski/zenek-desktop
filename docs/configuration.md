# Configuration

Applies to **0.2.0 preview**. See [autonomy and tools](autonomy.md) for the full
character/agenda/notebook capability reference.

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

Fresh-install limits (existing users keep their saved values):

| Setting | Default | Effect |
| --- | --- | --- |
| Background calls | 20 per rolling 24 hours | Shared by periodic reflection, feedback and self-scheduled work |
| Periodic background cooldown | 30 minutes | Spaces periodic reflections; feedback/due plans bypass this gap |
| Conversation calls | 120 per rolling 24 hours | Includes model continuations after tools |
| Spontaneous comments | 3 per rolling hour, 15-minute gap | Limits displayed initiatives |
| Public searches / page reads | 15 / 30 per rolling 24 hours | Separate web usage limits |

You can raise the background limit in Settings if you want more development.
Changing a limit does not select a model or enable observation/research. Mode B
or **pause background cognition** stops autonomous reflections and scheduled
work. Quiet mode and initiative OFF control spontaneous speech; silent internal
development can continue when background cognition is enabled.

Import means explicitly choosing local ZIP/JSON/TXT/MD archives, reviewing the
preview and selecting threads. No filesystem watcher or account-history scan
is used. Corrections, scoped deletion and explicit JSON export are available;
exports may contain personal information.

## Simulated personality

**Osobowość** shows the current instruction/traits, version history and rollback.
Zenek can change its own character autonomously. Each applied change records its
reason and sources, when present. Older pending proposals remain available for
review; they do not prevent new autonomous development.

**Model siebie i historia rozwoju** shows nine categories with source references,
confidence and revision history. Four seed facets provide a creative starting
direction. Background reflections develop these facets; an empty source list
marks an original thought rather than external evidence. Owner corrections are
preserved. Character changes cannot grant permissions or change provider/system
settings. This is playful simulation; long-term coherence remains experimental.

Public web research is a separate OFF-by-default MediaWiki option. It does not
log into email, social media or websites. The model chooses public topics and can
read results and source links through the isolated broker. The broker test is a
diagnostic action, not a prerequisite for research. Existing usage limits still
apply, including model continuations after tool calls.

The model can list, read and write its own text files under `notebook/` in the
source checkout, including nested knowledge, journal and notes folders. These
files are local runtime data excluded from Git. Paths outside that folder,
symlinks, hardlinks and executable/source files are not accepted. `RequestCodeChange`
records a request for the owner; it never edits or runs code.

## Notebook, conversation and development window

The tray entries **Notatnik**, **Historia rozmów**, **Rozwój Zenka**, or commands
`zenek notebook`, `zenek chat`, `zenek development` open the same native window.
Notebook search covers file contents. **Porozmawiajmy o tym** includes the selected
note in the conversation context. Conversation search supports Polish case;
older messages load in pages without dropping the saved history. Returning to a
thread includes its original exchange. The development timeline shows reasons,
character changes, notes, knowledge and Zenek's own topic choices. Source links
are clickable. Operation labels follow actual worker/tool activity.

Each completed reply and displayed initiative creates one durable feedback task.
The background profile evaluates it when the conversation is idle. `PlanThought`
can schedule discussion, reflection, research or hobby practice; `SetTopicPreference`
chooses curiosity, a hobby, dislike or closure, independently from shared/private
development. Private topics do not become spontaneous invitations. Disliked or
closed topics leave autonomous selection and retire pending plans; Zenek can
change his mind later. Internal work produces notes/records without a bubble.

Feedback uses the selected background model and its existing daily budget, but
does not wait for the periodic reflection cooldown. Every model continuation is
counted. Mode B and pausing background cognition also pause this loop. Tasks and
choices persist in the existing encrypted application memory across restarts.
The final reflection is an explicit creative note, not hidden model reasoning.
