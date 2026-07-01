from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalSocket

from process_utils import ipc_server_name

_socket: QLocalSocket | None = None
_pending: list[bytes] = []


def _ensure_socket():
    global _socket
    if _socket is not None and _socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
        return
    if _socket is None:
        _socket = QLocalSocket()
        _socket.disconnected.connect(_on_disconnected)
        _socket.errorOccurred.connect(_on_error)
    if _socket.state() != QLocalSocket.LocalSocketState.ConnectedState:
        _socket.connectToServer(ipc_server_name())
        # Non-blocking: OS will connect asynchronously


def _on_disconnected():
    QTimer.singleShot(500, _ensure_socket)


def _on_error(_error):
    QTimer.singleShot(500, _ensure_socket)


def _write(data: bytes):
    _ensure_socket()
    if _socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
        _socket.write(data)
        _socket.flush()
    else:
        _pending.append(data)
        if len(_pending) > 50:
            _pending[:] = _pending[-25:]


def publish_action(character: str, action: str):
    if not character or not action:
        return
    try:
        _write(f"ACTION\t{character}\t{action}\n".encode("utf-8"))
    except Exception:
        pass


def publish_lip_sync(character: str, level: float):
    if not character:
        return
    try:
        level = max(0.0, min(float(level), 1.0))
        _write(f"LIP\t{character}\t{level:.3f}\n".encode("utf-8"))
    except Exception:
        pass
