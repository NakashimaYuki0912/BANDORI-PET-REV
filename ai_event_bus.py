import json

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalSocket

from process_utils import ipc_server_name

_socket: QLocalSocket | None = None


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


def _on_disconnected():
    QTimer.singleShot(500, _ensure_socket)


def _on_error(_error):
    QTimer.singleShot(500, _ensure_socket)


def publish_ai_event(data: dict):
    if not isinstance(data, dict):
        return
    try:
        _ensure_socket()
        payload = json.dumps(data, ensure_ascii=False)
        _socket.write(f"AI_EVENT\t{payload}\n".encode("utf-8"))
        _socket.flush()
    except Exception:
        pass
