# Changelog

All notable changes to this project are recorded here. Versions follow Semantic
Versioning while the project remains a preview.

## [Unreleased]

## [0.2.0] - 2026-10-18

Autonomous character development and a native notebook/conversation workspace.

- Conversation and background profiles can call scoped memory, knowledge,
  character, notebook, agenda and optional public-research tools. Responses
  function calls continue with their outputs; each inference round consumes
  the selected profile's existing budget.
- Zenek applies character changes autonomously, preserving reasons, sources,
  version history and rollback. Earlier pending proposals remain reviewable.
- Durable feedback after replies and displayed initiatives supports silent
  reflection, scheduled research/practice, private hobbies and topic closure.
  Self-scheduled work uses the background budget without the periodic cooldown.
- Local `notebook/` text files support knowledge, journals and hobby notes;
  traversal, links and source/executable extensions are rejected. Notebook
  contents are private runtime data excluded from public source.
- Native notebook, conversation and development views add content search,
  Polish case matching, paged history, source links and returning to a note or
  earlier exchange. Open them from the tray, CLI or bubble's larger-window button.
- Activity labels reflect actual workers/tools. Code changes remain owner-only;
  Zenek can record a request but cannot edit or execute code.
- Public research accepts dynamically chosen general topics rather than a fixed
  three-topic catalog. The sandbox test is diagnostic; the separate research
  switch, query checks and usage limits still apply.
- Updated installation, configuration, architecture, privacy, testing and roadmap
  documentation; added autonomy/tool and maintainer release guides.

This is still a GNOME 50 / Wayland preview with Polish UI/persona and source-only
distribution. Existing model selections, limits, memory and explicit OFF choices
are preserved on update. See [update instructions](docs/installation.md#update-and-uninstall).

## [0.1.0] - 2026-10-12

Initial public preview, following local desktop testing.

- GNOME Shell 50 companion with ZENN animations and an inline conversation bubble.
- Python Core, GTK4/libadwaita settings, per-user service and encrypted SQLCipher memory.
- Independent conversation, background and vision profiles with Sign in with ChatGPT.
- Optional periodic screenshots, local OCR/redaction and graphics-based vision routing.
- Persistent screenshot preference and tray controls, including safe session recovery.
- Topic variety and a nine-category simulated self model with sources and revision history.
- Explicit archive import, memory corrections/export and personality proposals with rollback.
- Optional sandboxed read-only public web research.
- Public documentation, Apache-2.0 licensing, contribution guidelines and automated CI.

GNOME 50 / Wayland only. Polish UI/persona. No PyPI, app-store or GNOME Extensions
catalog distribution is claimed. See [known limitations](docs/testing.md).

[Unreleased]: https://github.com/piotr-adamski/zenek-desktop/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/piotr-adamski/zenek-desktop/releases/tag/v0.2.0
[0.1.0]: https://github.com/piotr-adamski/zenek-desktop/releases/tag/v0.1.0
