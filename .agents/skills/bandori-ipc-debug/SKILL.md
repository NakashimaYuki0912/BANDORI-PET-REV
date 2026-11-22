---
name: bandori-ipc-debug
description: >-
  Use this skill when debugging IPC communication between BandoriPet processes, 
  diagnosing action/lip-sync/AI-event delivery failures, or understanding the 
  multi-process architecture. Covers QLocalSocket protocol, message format parsing, 
  and cross-process log correlation.
---

# BandoriPet IPC Debug Guide

## Architecture Overview

BandoriPet runs each desktop pet character in an **independent Python process**. 
Communication uses **QLocalSocket** (named pipes on Windows).

```
┌──────────────┐       QLocalSocket IPC        ┌──────────────┐
│  main.py     │◄──────────────────────────────│  pet_process  │
│  (IPC Server)│       Named Pipe              │  (per char)   │
│              │◄──────────────────────────────│  settings_    │
│              │                                │  process      │
└──────────────┘                                └──────────────┘
       ▲                                              │
       │        ┌──────────────────┐                   │
       └────────│  action_bus.py   │◄──────────────────┘
                │  ai_event_bus.py │
                └──────────────────┘
```

## IPC Server Name

The IPC server name is **dynamically generated** from the install directory hash:

```python
# From process_utils.py
import hashlib
digest = hashlib.sha1(str(app_base_dir()).encode("utf-8")).hexdigest()[:12]
server_name = f"BandoriPet-{digest}"
```

This means different installs have different pipe names — useful for running 
multiple instances but can cause confusion when debugging.

## Message Protocol

All IPC messages are **text-line protocol** (`\n` terminated, `\t` separated):

### ACTION — Trigger Live2D Animation
```
ACTION\t<character_key>\t<action_name>\n
```
Example: `ACTION\tkasumi\thappy\n`

### LIP — Lip Sync Level
```
LIP\t<character_key>\t<level>\n
```
- `level`: float 0.0–1.0, mouth open amount
- Example: `LIP\tkasumi\t0.7\n`

### AI_EVENT — AI Status Push
```
AI_EVENT\t<json_payload>\n
```
Example: `AI_EVENT\t{"type":"thinking","character":"kasumi"}\n`

## Debugging Steps

### 1. Verify IPC Server is Running

Check if the named pipe exists (PowerShell):
```powershell
Get-ChildItem "\\.\pipe\" | Where-Object Name -like "*BandoriPet*"
```

### 2. Check IPC Server Name Match

Both client and server must compute the **same** `ipc_server_name()`:
```python
from process_utils import ipc_server_name
print(ipc_server_name())  # Should match on both sides
```

### 3. Monitor IPC Messages

Add temporary logging in `main.py` at the IPC message handler:
```python
# Look for the QLocalSocket readyRead handler
# Add: print(f"[IPC] Received: {data!r}")
```

### 4. Test Action Delivery

Use `action_bus.py` directly:
```python
from action_bus import send_action
send_action("kasumi", "happy")
```

### 5. Test AI Event Delivery

Use `ai_event_bus.py` or the CLI tool:
```bash
python bandori_ai_event.py --type thinking --character kasumi
```

## Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Actions not triggering | IPC server not started | Ensure `main.py` starts before pets |
| Wrong character receives action | Character key mismatch | Check key spelling (lowercase English) |
| Connection refused | Different install paths | Both processes must resolve same `app_base_dir()` |
| Messages arriving garbled | Encoding issue | Ensure UTF-8 on both ends |
| AI events lost | JSON parse error | Validate JSON payload before sending |

## HTTP Endpoints (Alternative Communication)

| Port | Purpose | File |
|------|---------|------|
| `38473` | Chat Integration Webhook (QQ/WeChat) | `chat_integration_server.py` |
| `38472` | AI Status Event Receiver | `ai_status_server.py` |

These are **not** IPC — they accept external HTTP requests and bridge them into 
the IPC system internally.

## Key Source Files

- [process_utils.py](../../process_utils.py) — `ipc_server_name()`, process launch helpers
- [action_bus.py](../../action_bus.py) — Send ACTION/LIP messages
- [ai_event_bus.py](../../ai_event_bus.py) — Send AI_EVENT messages
- [main.py](../../main.py) — IPC server listener
- [bandori_ai_event.py](../../bandori_ai_event.py) — CLI tool for AI events
