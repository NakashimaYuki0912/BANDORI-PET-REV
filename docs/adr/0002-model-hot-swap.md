# ADR-0002: In-place Live2D model hot-swap for same-character costume changes

## Status

Accepted (2026-07-03)

## Context

The original costume change flow always killed and restarted the pet process: settings panel sent `MODEL\t<char>\t<costume>\tRELAUNCH` → main process killed all pet processes → spawned new processes with the updated models. This was reliable but caused a visible window close-and-reopen flash, and cost 2-3 seconds of process startup time.

A `_switch_model(character, costume)` method existed in `pet_window.py` (line 1242) that could swap the Live2D model in-place — calling `Live2DWidget.set_model_path()` which reuses the existing OpenGL context and `LAppModel` instance. But this method had **zero callers** anywhere in the codebase.

The `Live2DWidget` already supported hot-reloading: `_load_model_internal()` skips creating a new `LAppModel` if one already exists, and calls `LoadModelJson()` on the existing instance.

## Decision

Enable in-place hot-swap for same-character costume changes:

1. **settings_process.py**: Remove the auto-append of `\tRELAUNCH` to MODEL messages. Main process decides whether to hot-swap or relaunch.
2. **main.py**: In `on_model_selected()`, check if the selected character already has a running pet process. If yes → broadcast `MODEL\t<char>\t<costume>` to all pet IPC clients (hot-swap). If no (different character) → full `launch_pet()`.
3. **pet_window.py**: Add a `MODEL` handler in `_handle_ipc_line()` that calls `_switch_model()` when the character matches.

Track running characters via `pet_window_ref["chars"]` set, populated in `launch_pet()`.

## Consequences

- **Positive**: Same-character costume changes are seamless — no window flash, no process restart, ~100ms to swap vs. 2-3 seconds.
- **Positive**: The `_switch_model` dead code is now live and tested.
- **Negative**: Different-character changes still require full restart (each pet process hosts one character).
- **Negative**: If the hot-swap IPC message is lost, the costume change silently fails. Broadcasting to all clients (not targeted) is a trade-off for simplicity — every pet receives the message and only the matching one acts on it.
