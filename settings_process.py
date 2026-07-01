import argparse
import os
import sys

from process_utils import app_base_dir, ipc_server_name, set_windows_app_user_model_id

BASE_DIR = str(app_base_dir())

_log_path = os.path.join(BASE_DIR, "settings_error.log")
sys.stderr = open(_log_path, "w", encoding="utf-8", buffering=1)

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication

from config_manager import ConfigManager
from i18n_manager import detect_system_language, set_language
from model_manager import ModelManager, models_dir_exists, prompt_download_model_resources
from settings_window import SettingsWindow
from app_theme import apply_app_theme


def _parse_args():
    parser = argparse.ArgumentParser(description="Run the settings window in an isolated process.")
    parser.add_argument("--character", default="")
    parser.add_argument("--costume", default="")
    parser.add_argument("--fps", type=int, default=120)
    parser.add_argument("--opacity", type=float, default=1.0)
    parser.add_argument("--vsync", choices=("0", "1"), default="1")
    parser.add_argument("--show-launch", choices=("0", "1"), default="0")
    parser.add_argument("--start-on-costumes", choices=("0", "1"), default="0")
    parser.add_argument("--hidden", action="store_true", help="Start hidden, wait for SHOW command")
    return parser.parse_args()


def _apply_app_icon(app: QApplication) -> None:
    icon_path = os.path.join(BASE_DIR, "logo.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))


class _StdinReader(QThread):
    """Reads SHOW/QUIT commands from stdin sent by the main process."""
    command = Signal(str)

    def run(self):
        try:
            for line in sys.stdin:
                cmd = line.strip()
                if cmd:
                    self.command.emit(cmd)
                    if cmd == "QUIT":
                        break
        except Exception:
            pass


class _HideOnCloseFilter(QObject):
    """Intercepts close events and hides the window instead of closing it."""
    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.Close:
            obj.hide()
            return True
        return False


def main():
    os.chdir(BASE_DIR)
    args = _parse_args()

    cfg = ConfigManager()
    set_language(cfg.get("language", "") or detect_system_language())

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    if sys.platform != "darwin":
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)

    set_windows_app_user_model_id("BandoriPet.Settings")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep process alive when window is hidden

    if sys.platform == "darwin":
        import macos_patch
        macos_patch.hide_dock_icon()
    app.setApplicationName("BandoriPetSettings")
    app.setOrganizationName("BandoriPet")
    _apply_app_icon(app)

    apply_app_theme(cfg.get("dark_theme", False))

    if not models_dir_exists():
        prompt_download_model_resources()
        return 0

    ipc_socket = QLocalSocket(app)
    ipc_socket.connectToServer(ipc_server_name())

    def send_ipc_line(line: str):
        if ipc_socket.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            ipc_socket.connectToServer(ipc_server_name())
        if ipc_socket.state() != QLocalSocket.LocalSocketState.ConnectedState:
            ipc_socket.waitForConnected(200)
        if ipc_socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            ipc_socket.write((line + "\n").encode("utf-8"))
            ipc_socket.flush()
            ipc_socket.waitForBytesWritten(200)

    # Exit when main process IPC socket disconnects
    def _on_ipc_disconnected():
        app.quit()
    ipc_socket.disconnected.connect(_on_ipc_disconnected)

    mgr = ModelManager()
    window = SettingsWindow(
        mgr,
        current_char=args.character,
        current_costume=args.costume,
        current_fps=args.fps,
        current_opacity=args.opacity,
        show_launch=args.show_launch == "1",
        start_on_costumes=args.start_on_costumes == "1",
        config_manager=cfg,
        vsync=args.vsync == "1",
        live2d_module=None,
    )
    window.connect_ipc_output(send_ipc_line)

    # Hide instead of close so the process stays warm for next open
    hide_filter = _HideOnCloseFilter(app)
    window.installEventFilter(hide_filter)

    screen = app.primaryScreen()
    if screen:
        geo = screen.availableGeometry()
        window.move((geo.width() - window.width()) // 2, (geo.height() - window.height()) // 2)

    if args.hidden:
        window.hide()
    else:
        window.show()

    # Listen for SHOW/QUIT from main process via stdin
    stdin_reader = _StdinReader()

    def _handle_command(cmd: str):
        try:
            if cmd == "SHOW":
                window.show()
                window.raise_()
                window.activateWindow()
            elif cmd == "SHOW_COSTUMES":
                window.show()
                window.raise_()
                window.activateWindow()
                char = (
                    window._selected_list_character
                    or window._current_char
                    or (mgr.characters[0] if mgr.characters else "")
                )
                if char:
                    window._selected_list_character = char
                    window._switch_costume_direct()
            elif cmd == "QUIT":
                app.quit()
        except Exception:
            import traceback
            traceback.print_exc()
            sys.stderr.flush()

    stdin_reader.command.connect(_handle_command)
    stdin_reader.start()

    return app.exec()


if __name__ == "__main__":
    import datetime
    sys.stderr.write(f"\n--- settings_process.py start {datetime.datetime.now()} ---\n")
    sys.stderr.flush()
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        sys.exit(1)
