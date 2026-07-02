"""
SSH tunnel: forwards localhost:9880 → kirby@vanillatte.cafe:9880.

────────────────────────────────────────────────────────────────────────────
HOW TO SIMPLIFY (one-time setup, then no password ever again):

  1. Open PowerShell and run:
       ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\bandori_key" -N '""'

  2. Upload the public key to the server (enter password once here):
       type "$env:USERPROFILE\.ssh\bandori_key.pub" | ssh -p 65022 kirby@vanillatte.cafe "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

  3. The key file will be detected automatically next time the pet starts.
     No further configuration needed.
────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import socket
import subprocess
import threading
import time

# ── Connection config ────────────────────────────────────────────────────────
_SSH_HOST = "vanillatte.cafe"
_SSH_PORT = 65022
_SSH_USER = "kirby"
_SSH_PASS = "Iloveyou,too"
_LOCAL_PORT = 9880
_REMOTE_PORT = 9880
_SSH_KEY = os.path.join(os.path.expanduser("~"), ".ssh", "bandori_key")
# ─────────────────────────────────────────────────────────────────────────────

_tunnel_obj = None      # SSHTunnelForwarder (password mode)
_proc = None            # subprocess.Popen (key mode)
_watchdog_thread = None
_stop_watchdog = threading.Event()
_lock = threading.Lock()


def _port_open(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False


def _use_key_auth() -> bool:
    return os.path.isfile(_SSH_KEY)


# ── Key-based auth (subprocess ssh) ─────────────────────────────────────────

def _start_key_auth() -> bool:
    global _proc
    if _proc is not None and _proc.poll() is None:
        return True
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        _proc = subprocess.Popen(
            [
                "ssh", "-NL", f"{_LOCAL_PORT}:localhost:{_REMOTE_PORT}",
                "-p", str(_SSH_PORT),
                "-i", _SSH_KEY,
                f"{_SSH_USER}@{_SSH_HOST}",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ServerAliveInterval=30",
                "-o", "ServerAliveCountMax=3",
                "-o", "ExitOnForwardFailure=yes",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        return True  # non-blocking: process started, port may take a moment
    except Exception as e:
        print(f"[ssh_tunnel] key-auth start error: {e}")
        return False


def _watchdog_key():
    """Restart the ssh process if it exits unexpectedly."""
    while not _stop_watchdog.is_set():
        _stop_watchdog.wait(15)
        if _stop_watchdog.is_set():
            break
        with _lock:
            if _proc is not None and _proc.poll() is not None:
                print("[ssh_tunnel] tunnel process exited, restarting…")
                _start_key_auth()


# ── Password-based auth (sshtunnel / paramiko) ───────────────────────────────

def _ensure_sshtunnel():
    try:
        import sshtunnel  # noqa: F401
        return True
    except ImportError:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "sshtunnel"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            print(f"[ssh_tunnel] could not install sshtunnel: {e}")
            return False


def _start_password_auth() -> bool:
    global _tunnel_obj
    if not _ensure_sshtunnel():
        return False
    from sshtunnel import SSHTunnelForwarder
    try:
        if _tunnel_obj is not None and _tunnel_obj.is_active:
            return True
        server = SSHTunnelForwarder(
            (_SSH_HOST, _SSH_PORT),
            ssh_username=_SSH_USER,
            ssh_password=_SSH_PASS,
            remote_bind_address=("localhost", _REMOTE_PORT),
            local_bind_address=("localhost", _LOCAL_PORT),
            set_keepalive=30,
        )
        server.start()
        _tunnel_obj = server
        return True
    except Exception as e:
        print(f"[ssh_tunnel] password-auth start error: {e}")
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def start() -> bool:
    """
    Start the SSH tunnel in background. Returns True immediately if port already
    open or process launched; False on password-auth failure.
    """
    global _watchdog_thread

    if _port_open(_LOCAL_PORT):
        return True

    with _lock:
        if _use_key_auth():
            ok = _start_key_auth()
            if ok and (_watchdog_thread is None or not _watchdog_thread.is_alive()):
                _stop_watchdog.clear()
                _watchdog_thread = threading.Thread(
                    target=_watchdog_key, name="ssh-tunnel-watchdog", daemon=True
                )
                _watchdog_thread.start()
            return ok
        else:
            return _start_password_auth()


def stop():
    """Tear down the tunnel gracefully."""
    global _tunnel_obj, _proc
    _stop_watchdog.set()
    with _lock:
        if _tunnel_obj is not None:
            try:
                _tunnel_obj.stop()
            except Exception:
                pass
            _tunnel_obj = None
        if _proc is not None:
            try:
                _proc.terminate()
                _proc.wait(timeout=4)
            except Exception:
                try:
                    _proc.kill()
                except Exception:
                    pass
            _proc = None
