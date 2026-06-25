# AGENTS.md

## Project overview

This project is a Windows desktop application written in Python 3.14.

The application uses a multipage Tkinter GUI and can work with several optional hardware and software integrations. Support for each integration can be enabled or disabled in `config/config.cfg` under the `features` section.

Optional integrations include:

* Cloud storage: Microsoft OneDrive
* Presentation app: Microsoft PowerPoint
* Video recording app: OBS Studio
* Hardware green screen keyer: Blackmagic Ultimatte
* Web browser: Mozilla Firefox
* Controller: Stream Deck

## General instructions

* Make minimal, high-confidence changes.
* Prefer small, targeted fixes over broad refactors.
* First understand the existing code path before changing behavior.
* Preserve existing public behavior unless a change is clearly required to fix a bug.
* Respect feature flags in `config/config.cfg`.
* Do not assume optional software or hardware is installed or available.
* Do not trigger real hardware, external applications, recordings, browser automation, or cloud operations during tests unless explicitly requested by the user.

## Bug fixing

* Identify the root cause before applying a fix.
* Keep fixes localized to the affected code.
* Avoid changing unrelated files.
* If a bug involves an optional integration, ensure the disabled-feature path still works.
* Add or update tests that would have caught the bug.

## Security

* Look for security issues such as unsafe file handling, path traversal, command injection, insecure subprocess usage, unsafe config parsing, credential leakage, and uncontrolled access to external applications.
* Report security concerns clearly and propose practical mitigations.
* Do not log secrets, tokens, credentials, local user paths, or sensitive configuration values.
* Avoid hardcoding credentials or machine-specific paths.

## Testing

* Use `pytest` for unit tests.
* Add tests for new or changed behavior.
* Mock hardware, GUI side effects, network access, cloud storage, OBS, PowerPoint, Firefox, Stream Deck, and Blackmagic Ultimatte integrations.
* Tests should not require real external applications, physical devices, or user-specific configuration.
* Prefer deterministic tests that can run in isolation.

## Code style

* Follow PEP 8.
* Use clear names and simple control flow.
* Add docstrings to new or modified public functions and classes when they are missing.
* Keep comments useful and close to the code they explain.
* Avoid unnecessary rewrites, formatting-only changes, or large-scale cleanup unless explicitly requested.

## Tkinter and Windows-specific guidance

* Keep GUI updates on the Tkinter main thread.
* Avoid blocking the GUI event loop with long-running work.
* Use `pathlib` where practical for filesystem paths.
* Be careful with Windows-specific paths, quoting, subprocess calls, and file locking.
* Do not assume administrator privileges.

## Guardrails

* Do not refactor large amounts of code or entire files unless explicitly asked.
* Do not overwrite recent user edits.
* Do not make git commits without user approval.
* Do not change configuration defaults without a clear reason.
* Do not remove support for optional integrations unless explicitly requested.
* When uncertain, explain the uncertainty and choose the smallest safe change.
