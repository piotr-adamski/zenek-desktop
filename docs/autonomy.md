# Autonomy and tools

In **0.2.0 preview**, Zenek can develop a fictional character, learn, keep notes
and choose activities. Its self model is a playful simulation. No claim of
subjective experience is required for the feature.

## What develops

The active character prompt and ten numerical traits can change autonomously.
Every applied version retains the prior version, actor, reason and source IDs
when supplied; Settings offers history and rollback. Owner corrections to self
facets are preserved. Older proposals remain reviewable, while new character
changes do not wait in an approval queue.

Nine self-model categories organize identity, values, beliefs, questions, taste,
aspirations, tensions, relationship and metacognition. Categories contain named
domains, confidence, source references, related facets and revision history.
An original thought can have no external source; it is not evidence of an event
or of a fact about the owner. Repeated screen content is not a new source of proof.

## Choices and plans

After a completed reply or displayed model initiative, one persistent feedback
task lets the background model reconsider its own contribution. It may leave a
short explicit reflection, change direction, research, write, schedule something
or remain silent. This record is an authored character note, not hidden reasoning.
Internal reflections do not recursively enqueue utterance feedback.

`SetTopicPreference` chooses **curious**, **hobby**, **dislike** or **closed**,
with independent **shared/private** visibility for spontaneous invitations.
Private topics develop silently but remain readable by the owner. Disliked or
closed topics leave automatic selection; pending work is retired when examined.
Zenek can later change its mind.

`PlanThought` schedules **discuss**, **reflect**, **research** or **practice**.
Discussion enters normal invitation selection; private discussion becomes an
internal reflection. Due internal plans wait for an idle worker/session and an
available background budget. They bypass the periodic reflection cooldown, not
the daily budget. A plan can persist across restart without promising an exact
execution time. Work can pause, be cancelled or produce no new note.

## Model capabilities

Conversation and background profiles receive these scoped functions; vision
requests do not receive this tool set. WWW functions appear only when research
is enabled.

| Tool | Effect |
| --- | --- |
| `RecallMemory` | Recall bounded local context and the active character |
| `RememberKnowledge` | Save sourced knowledge or a labeled original inference |
| `UpdateInterest` | Add/update an interest and its general public research query |
| `EvolvePersonality` | Apply a character/trait version with a reason and history |
| `RequestCodeChange` | Record an owner-facing request; never edit or execute code |
| `ListNotes`, `ReadNote`, `WriteNote` | List/read/create or replace notebook text |
| `SetTopicPreference` | Choose interest, hobby, dislike/closure and shared/private |
| `PlanThought` | Persist a later discussion, reflection, research or practice task |
| `SearchPublicWeb` | Search public Wikipedia topics through the isolated broker |
| `ReadPublicPage` | Read a validated search result or discovered source link |

Each model continuation after tool output consumes another call from the
selected profile's budget. There is no automatic model substitution or paid
fallback. Web searches/page reads have separate counters too.

## Notebook and reading window

Notes live under `notebook/` in the installed source checkout. Nested knowledge,
journal and hobby directories are supported. Accepted extensions are `.md`,
`.txt`, `.json`, `.jsonl`, `.csv` and `.tsv`; a write replaces the named file.
Absolute/traversal/hidden paths, symlinks, hardlinks and other extensions are
rejected. This directory is ordinary local text, excluded from Git and releases.

Open **Notatnik**, **Historia rozmów** or **Rozwój Zenka** from the tray, or use:

```bash
zenek notebook
zenek chat
zenek development
```

The notebook searches file contents; **Porozmawiajmy o tym** sends a new turn with
the selected note as context. Conversation search supports Polish case, loads
older messages in pages and offers **Wróćmy do tego wątku**. The development view
shows reasons, before/after character text, trait changes, notes and own choices.
Source links open in your browser. **Większe okno** in the bubble opens the
conversation view. Activity labels follow actual worker/tool state.

## Controls and boundaries

Configure independent profiles and limits in [Settings](configuration.md).
Background mode B or background pause stops model reflections and due internal
work. Quiet/initiative controls affect spontaneous speech. The separate WWW
switch controls research; disabling observation affects screen context.

Character tools cannot modify code, run shell commands, grant permissions or
change model/provider settings. There is no generic filesystem, email, clipboard
or account-history tool. Public-query validation is heuristic; enable research
with the [privacy limitations](privacy.md) in mind. Notebook files need a separate
backup from SQLCipher. Long-term coherence, topic diversity and hobby continuity
remain experimental.
