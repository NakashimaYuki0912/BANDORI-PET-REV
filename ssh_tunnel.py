"""Manage the optional SSH tunnel used by the remote GPT-SoVITS backend.

The SSH transport reaches ``server.vanillatte.cafe`` over its AAAA record,
while the forwarded service remains available to BandoriPet on the local IPv4
loopback address ``127.0.0.1:9880``.  Do not add OpenSSH's global ``-6`` flag:
on Windows it also forces the local forwarding listener to IPv6 and makes the
IPv4 bind fail.

Automatic startup is deliberately public-key-only.  OpenSSH may use
``~/.ssh/bandori_key``, another default identity, or an ssh-agent.  Passwords
must never be stored in this repository.  A manually established tunnel is
also supported; :func:`start` simply reuses an existing local listener.

Environment overrides are available for local installations:

``BANDORI_TTS_SSH_HOST``, ``BANDORI_TTS_SSH_PORT``,
``BANDORI_TTS_SSH_USER``, and ``BANDORI_TTS_SSH_KEY``.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time


def _env_port(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return value


_SSH_HOST = os.environ.get(
    "BANDORI_TTS_SSH_HOST",
    "server.vanillatte.cafe",
).strip()
_SSH_PORT = _env_port("BANDORI_TTS_SSH_PORT", 22)
_SSH_USER = os.environ.get("BANDORI_TTS_SSH_USER", "kirby").strip()
_LOCAL_HOST = "127.0.0.1"
_LOCAL_PORT = 9880
_REMOTE_HOST = "127.0.0.1"
_REMOTE_PORT = 9880
_DEFAULT_SSH_KEY = os.path.join(
    os.path.expanduser("~"),
    ".ssh",
    "bandori_key",
)

_STARTUP_TIMEOUT = 8.0
_WATCHDOG_INTERVAL = 15.0

_proc: subprocess.Popen | None = None
_watchdog_thread: threading.Thread | None = None
_stop_watchdog = threading.Event()
_lock = threading.Lock()
_last_error = ""


def _set_last_error(message: str) -> None:
    global _last_error
    _last_error = " ".join(str(message or "").split())[:500]


def last_error() -> str:
    """Return the latest sanitized startup or reconnect error."""
    return _last_error


def _port_open(port: int = _LOCAL_PORT) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((_LOCAL_HOST, port)) == 0
    except OSError:
        return False


def _configured_key_path() -> str | None:
    configured = os.environ.get("BANDORI_TTS_SSH_KEY", "").strip()
    if configured:
        path = os.path.abspath(os.path.expanduser(configured))
        if not os.path.isfile(path):
            raise FileNotFoundError(
                "BANDORI_TTS_SSH_KEY does not point to an existing file"
            )
        return path
    if os.path.isfile(_DEFAULT_SSH_KEY):
        return _DEFAULT_SSH_KEY
    return None


def _build_ssh_command(key_path: str | None) -> list[str]:
    """Build an argument-safe OpenSSH command.

    The destination is intentionally appended last.  Every preceding element
    is a local OpenSSH option rather than an accidental remote command.
    """
    if not _SSH_HOST or not _SSH_USER:
        raise ValueError("SSH host and user must not be empty")

    forward = (
        f"{_LOCAL_HOST}:{_LOCAL_PORT}:"
        f"{_REMOTE_HOST}:{_REMOTE_PORT}"
    )
    command = [
        "ssh",
        "-N",
        "-T",
        "-L",
        forward,
        "-p",
        str(_SSH_PORT),
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "ConnectTimeout=6",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "LogLevel=ERROR",
    ]
    if key_path:
        command.extend(["-i", key_path, "-o", "IdentitiesOnly=yes"])
    command.append(f"{_SSH_USER}@{_SSH_HOST}")
    return command


def _friendly_ssh_error(stderr: str, return_code: int | None) -> str:
    detail = " ".join(str(stderr or "").split())
    lowered = detail.lower()
    if "host key verification failed" in lowered:
        return (
            "SSH host key is not trusted. Connect to "
            f"{_SSH_USER}@{_SSH_HOST} once interactively and verify its key."
        )
    if "permission denied" in lowered:
        return (
            "SSH public-key authentication failed. Configure bandori_key, "
            "a default OpenSSH identity, or ssh-agent."
        )
    if detail:
        return detail[:500]
    if return_code is not None:
        return f"SSH exited before the tunnel was ready (code {return_code})."
    return "SSH tunnel did not become ready."


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=4)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=4)
        except Exception:
            pass


def _read_process_error(process: subprocess.Popen) -> str:
    try:
        _stdout, stderr = process.communicate(timeout=0.2)
    except Exception:
        return ""
    return str(stderr or "")


def _launch_ssh(
    *,
    wait_timeout: float = _STARTUP_TIMEOUT,
    key_path: str | None,
) -> bool:
    """Launch OpenSSH and return only after the local listener is ready."""
    global _proc

    if _proc is not None and _proc.poll() is None:
        if _port_open():
            return True
        _terminate_process(_proc)
        _proc = None

    _set_last_error("")
    try:
        command = _build_ssh_command(key_path)
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
        )
    except (OSError, ValueError) as exc:
        _set_last_error(f"Unable to start OpenSSH: {exc}")
        print(f"[ssh_tunnel] {last_error()}")
        return False

    _proc = process
    deadline = time.monotonic() + max(0.0, wait_timeout)
    while True:
        if _port_open():
            return True

        return_code = process.poll()
        if return_code is not None:
            error = _friendly_ssh_error(
                _read_process_error(process),
                return_code,
            )
            if _proc is process:
                _proc = None
            _set_last_error(error)
            print(f"[ssh_tunnel] {error}")
            return False

        if time.monotonic() >= deadline:
            _terminate_process(process)
            if _proc is process:
                _proc = None
            error = (
                f"SSH tunnel did not listen on {_LOCAL_HOST}:{_LOCAL_PORT} "
                f"within {wait_timeout:g} seconds."
            )
            _set_last_error(error)
            print(f"[ssh_tunnel] {error}")
            return False

        time.sleep(0.1)


def _watchdog() -> None:
    global _proc

    while not _stop_watchdog.wait(_WATCHDOG_INTERVAL):
        with _lock:
            if _stop_watchdog.is_set():
                return
            if _port_open() and _proc is not None and _proc.poll() is None:
                continue
            if _proc is not None:
                if _proc.poll() is None:
                    _terminate_process(_proc)
                _proc = None
            try:
                key_path = _configured_key_path()
            except (OSError, ValueError) as exc:
                _set_last_error(str(exc))
                print(f"[ssh_tunnel] {last_error()}")
                continue
            print("[ssh_tunnel] tunnel disconnected; reconnecting")
            _launch_ssh(key_path=key_path)


def start() -> bool:
    """Start or reuse the local TTS tunnel.

    ``True`` means that ``127.0.0.1:9880`` is accepting connections.  It no
    longer means merely that an SSH child process happened to be created.
    """
    global _watchdog_thread

    if _port_open():
        return True

    with _lock:
        if _port_open():
            return True
        try:
            key_path = _configured_key_path()
        except (OSError, ValueError) as exc:
            _set_last_error(str(exc))
            print(f"[ssh_tunnel] {last_error()}")
            return False

        if not _launch_ssh(key_path=key_path):
            return False

        if _watchdog_thread is None or not _watchdog_thread.is_alive():
            _stop_watchdog.clear()
            _watchdog_thread = threading.Thread(
                target=_watchdog,
                name="ssh-tunnel-watchdog",
                daemon=True,
            )
            _watchdog_thread.start()
        return True


def stop() -> None:
    """Stop only the tunnel process owned by this module."""
    global _proc, _watchdog_thread

    _stop_watchdog.set()
    with _lock:
        process = _proc
        _proc = None
    if process is not None:
        _terminate_process(process)

    thread = _watchdog_thread
    _watchdog_thread = None
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=1.0)
