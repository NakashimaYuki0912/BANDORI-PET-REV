# Context — BandoriPet Domain Glossary

## Core concepts

- **Pet** — a desktop window displaying one Live2D character. Each pet runs in its own OS process spawned by the main process.
- **Main process** — the orchestrator (`main.py`). Manages the system tray, IPC server, HTTP servers, TTS backend, and spawns/kills pet/settings/chat subprocesses.
- **Pet process** — a child process (`pet_process.py`) hosting a single `PetWindow` with a `Live2DWidget` or `PixelPetWidget`. Communicates with main process via QLocalSocket IPC.
- **Settings process** — a child process (`settings_process.py`) hosting the `SettingsWindow`. Pre-warmed or launched on demand via main process commands. Uses stdin for show/hide commands.
- **Chat process** — a child process (`chat_process.py`) hosting the `ChatWindow`. Launched per pet when the user opens the character dialogue.

## Rendering

- **Live2DWidget** — the OpenGL widget that renders a Live2D character using the LuaJIT Live2D-v2-Lua rendering core. Lives inside a `PetWindow`.
- **PixelPetWidget** — a CPU-friendly alternative to `Live2DWidget`. Renders a character as a pixel-art sprite with wandering/idle animations.
- **Model** — a `.model.json` file inside a `models/<character>/<costume>/` directory (or virtual path inside a zst archive). Defines the Live2D model structure, textures, motions, and physics.
- **Costume** — a specific outfit variant for a character. Each costume has its own `model.json`. Characters can have multiple costumes.
- **ZST archive** — a `models/<character>.zst` compressed tar archive. Models inside are loaded via virtual paths without extracting to disk. Uses `zst_model_archive.py`.
- **Character key** — the lowercase identifier for a character (e.g., `kasumi`, `anon`, `tomorin`). Used in model directories, config entries, and IPC messages.
- **System prompt** — a per-character LLM prompt file in `characters/<key>/` that defines personality, speech patterns, and action tags.
- **Action tag** — a `[tagname]` annotation in LLM responses that triggers a specific Live2D motion or expression. Parsed by `live2d_click_actions.py`.

## IPC architecture

- **QLocalSocket IPC** — the main process hosts a `QLocalServer`. All subprocesses connect as clients. Messages are newline-delimited text with tab-separated fields.
- **action_bus** — module for sending ACTION and LIP messages from any process to the pet windows via IPC.
- **ai_event_bus** — module for sending AI_EVENT (status/overlay) messages to pet windows.
- **MODEL message** — IPC command `MODEL\t<character>\t<costume>` that triggers a hot-swap of the Live2D model in-place (same character) or a full pet process restart (different character). Relies on the MODEL handler in `pet_window._handle_ipc_line()`.
- **OPEN_SETTINGS message** — IPC command that requests main to open the settings panel, optionally starting on the costume page.
- **SHOW / SHOW_COSTUMES commands** — stdin commands sent from main process to the settings process to show the window, with `SHOW_COSTUMES` switching directly to the costume page.
- **Hot-swap** — an in-place model change triggered by a MODEL IPC message. The pet process calls `_switch_model()` in `pet_window.py` which calls `Live2DWidget.set_model_path()`, reusing the existing OpenGL context and `LAppModel` instance.

## UI components

- **Radial menu** — the right-click popup menu on a pet. Shows action items (chat, costume, weather, lock) as `RadialListRow` cards and an optional `MediaRadialItem` for now-playing media control.
- **RadialListRow** — a card-style row in the radial menu with a left color strip, icon area (hand-drawn line art), title, and subtitle. Uses QPainter for rendering.
- **MediaRadialItem** — the media control card in the radial menu showing now-playing track info and playback controls. Multiple visual styles (Aurora, Neon, Glass, etc.). Fixed at 310×144 pixels.
- **Compact AI window** — a floating overlay window showing AI status, synced per pet character.
- **Chat integration** — a local HTTP webhook server (`chat_integration_server.py`, port 38473) that receives forwarded messages from QQ/WeChat/Telegram/Discord bots.

## Data

- **config.json** — the singleton configuration file managed by `ConfigManager`. Contains all user settings: models, LLM profiles, TTS config, window positions, etc. Uses atomic writes via tempfile + fsync + os.replace.
- **data.db** — the SQLite database managed by `DatabaseManager`. Stores conversation history, relationship state (affection, trust, familiarity, mood), and character memories.
- **Conversation** — a thread of messages between the user and a character, identified by `conv_id` (1:1) or `group_conv_id` (group chat). Each message has a role (`user` or `assistant`), content, optional reasoning, and optional attachments.

## TTS

- **TTS backend** — a local Qwen3TTS or GPT-SoVITS server running on port 9880. Can be launched as a subprocess or connected via SSH tunnel.
- **SSH tunnel** — an SSH port forward (`vanillatte.cafe:9880 → localhost:9880`) for remote TTS access. Managed by `ssh_tunnel.py`.
- **Lip sync** — the TTS-driven mouth movement on the Live2D model. Lip sync levels (0.0–1.0) are sent via IPC as `LIP\t<character>\t<level>` messages at the audio frame rate.
