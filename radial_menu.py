import math
import ctypes
import os
import sys
from dataclasses import dataclass

if os.name == "nt":
    import ctypes.wintypes
from typing import Callable

from PySide6.QtCore import (
    Qt, Signal, QPoint, QSize, QPropertyAnimation, QEasingCurve, QTimer,
    QParallelAnimationGroup, QVariantAnimation, QRect, QRectF,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QMouseEvent,
    QRadialGradient, QLinearGradient, QFontMetrics, QPixmap, QCursor, QGuiApplication,
    QIcon, QPolygon, QPainterPath, QTransform,
)
from PySide6.QtWidgets import (
    QWidget, QGraphicsOpacityEffect, QPushButton, QLabel, QHBoxLayout,
    QVBoxLayout, QSizePolicy, QStyle, QFrame, QMenu,
)


from win32_constants import (
    DWMWA_WINDOW_CORNER_PREFERENCE, DWMWA_BORDER_COLOR,
    DWMWCP_DONOTROUND, DWMWA_COLOR_NONE,
    WM_NCCALCSIZE,
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED,
)

if os.name == "nt":
    _user32 = ctypes.windll.user32
    _set_window_pos = _user32.SetWindowPos
    _set_window_pos.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    _set_window_pos.restype = ctypes.wintypes.BOOL
    _get_async_key_state = _user32.GetAsyncKeyState
    _get_async_key_state.argtypes = [ctypes.c_int]
    _get_async_key_state.restype = ctypes.c_short
    _dwmapi = ctypes.windll.dwmapi
    _dwm_set_window_attribute = _dwmapi.DwmSetWindowAttribute
    _dwm_set_window_attribute.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
    ]
    _dwm_set_window_attribute.restype = ctypes.c_long
else:
    _set_window_pos = None
    _get_async_key_state = None
    _dwm_set_window_attribute = None

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04

MEDIA_CARD_WIDTH = 212
MEDIA_CARD_HEIGHT = 128
MEDIA_PANEL_INSET = 4
MEDIA_CARD_RADIUS = 20
MEDIA_CONTROL_SECONDARY_SIZE = 36
MEDIA_CONTROL_SECONDARY_HEIGHT = 30
MEDIA_CONTROL_PRIMARY_SIZE = 44
MEDIA_CONTROL_PRIMARY_HEIGHT = 30
MEDIA_CONTROL_GAP = 10
MEDIA_CONTROL_BOTTOM_MARGIN = 14
MEDIA_MENU_SIZE = 28
MEDIA_MENU_TOP_MARGIN = 10
MEDIA_MENU_RIGHT_MARGIN = 10
MEDIA_TITLE_LEFT_MARGIN = 14
MEDIA_TITLE_TOP_MARGIN = 14
MEDIA_TRACK_TOP_OFFSET = 21
MEDIA_TRACK_HEIGHT = 18

if sys.platform == "darwin":
    import macos_patch
else:
    macos_patch = None


class RadialMenuItem(QWidget):
    clicked = Signal()

    def __init__(self, icon_path: str, label: str, color: QColor,
                 glyph: str = "", enabled: bool = True, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._hover = False
        self._glyph = glyph
        self._icon = QPixmap(icon_path) if icon_path and os.path.exists(icon_path) else None
        self._enabled = enabled

        size = 80
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_label(self, label: str):
        if self._label == label:
            return
        self._label = label
        self.update()

    def set_glyph(self, glyph: str):
        if self._glyph == glyph:
            return
        self._glyph = glyph
        self.update()

    def set_enabled_state(self, enabled: bool):
        if self._enabled == enabled:
            return
        self._enabled = enabled
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor
        )
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 4

        color = self._color.lighter(130) if self._hover and self._enabled else self._color
        if not self._enabled:
            color = QColor(120, 120, 120)

        p.setPen(Qt.PenStyle.NoPen)

        gradient = QRadialGradient(cx, cy - r * 0.3, r * 1.2)
        gradient.setColorAt(0, color.lighter(150))
        gradient.setColorAt(0.7, color)
        gradient.setColorAt(1, color.darker(120))
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r))

        p.setBrush(QColor(255, 255, 255, 40 if self._hover else 10))
        p.drawEllipse(QPoint(int(cx), int(cy)), int(r * 0.85), int(r * 0.85))

        if self._icon and not self._icon.isNull():
            icon_size = int(r * 0.7)
            scaled = self._icon.scaled(
                icon_size, icon_size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            p.drawPixmap(int(cx - icon_size / 2), int(cy - icon_size / 2 - r * 0.15), scaled)
        elif self._glyph:
            font = p.font()
            font.setPointSize(22)
            p.setFont(font)
            p.setPen(QColor(255, 255, 255, 240))
            fm = QFontMetrics(font)
            g_w = fm.horizontalAdvance(self._glyph)
            p.drawText(int(cx - g_w / 2), int(cy - 2), self._glyph)

        font = p.font()
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 230))
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(self._label)
        p.drawText(int(cx - text_w / 2), int(cy + r * 0.55), self._label)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            self.clicked.emit()


# ------------------------------------------------------------------
# MediaRadialItem — media control card for radial menu left slot
# ------------------------------------------------------------------

_STYLE_SHEETS = {}

def _media_style_cute() -> str:
    return """
        QFrame#cute {
            background: qlineargradient(x1:0 y1:0, x2:0 y2:1,
                stop:0 #fff4fa, stop:0.48 #ffd9e9, stop:1 #ffc0d8);
            border: 1px solid rgba(238, 94, 149, 165);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: #b93672;
            font-size: 11px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: #513340;
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(255,255,255,232);
            border: 1px solid rgba(227,98,151,120);
            border-radius: 18px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(92, 54, 74, 160);
            border: 1px solid rgba(255,255,255,140);
            color: rgba(255,255,255,240);
            min-width: 30px; min-height: 30px;
            border-radius: 14px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: qlineargradient(x1:0 y1:0, x2:1 y2:1,
                stop:0 #ff8cc8, stop:1 #ef4d9b);
            border: 1px solid rgba(255,255,255,210);
            border-radius: 22px;
        }
        QPushButton:hover { background: rgba(255,255,255,250); }
        QPushButton:pressed { background: rgba(255,198,221,245); }
    """


def _media_style_cyber() -> str:
    return """
        QFrame#cyber {
            background: qlineargradient(x1:0 y1:0, x2:1 y2:1,
                stop:0 #171a26, stop:0.45 #121823, stop:1 #09131b);
            border: 1px solid rgba(72, 223, 232, 190);
            border-radius: 14px;
        }
        QLabel#mediaAppLabel {
            color: #65f2e7;
            font-size: 11px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: #d6fbff;
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(242,253,255,224);
            border: 1px solid rgba(75,225,232,150);
            border-radius: 18px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(7, 23, 32, 210);
            border: 1px solid rgba(101,242,231,170);
            color: rgba(216,255,252,240);
            min-width: 30px; min-height: 30px;
            border-radius: 14px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: qlineargradient(x1:0 y1:0, x2:1 y2:1,
                stop:0 #7efff2, stop:1 #57a5ff);
            border: 1px solid rgba(231,255,255,220);
            border-radius: 22px;
        }
        QPushButton:hover { background: rgba(255,255,255,248); border-color: rgba(120,248,241,210); }
        QPushButton:pressed { background: rgba(192,242,247,240); }
    """


def _media_style_minimal() -> str:
    return """
        QFrame#minimal {
            background: rgba(43,45,52,238);
            border: 1px solid rgba(255,255,255,86);
            border-radius: 18px;
        }
        QLabel#mediaAppLabel {
            color: rgba(255,255,255,214);
            font-size: 11px;
            font-weight: 650;
        }
        QLabel#mediaTrackLabel {
            color: rgba(255,255,255,242);
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(246,247,250,222);
            border: 1px solid rgba(255,255,255,108);
            border-radius: 18px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(255,255,255,90);
            color: rgba(255,255,255,232);
            min-width: 30px; min-height: 30px;
            border-radius: 14px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: rgba(255,255,255,238);
            border-radius: 22px;
        }
        QPushButton:hover { background: rgba(255,255,255,250); }
        QPushButton:pressed { background: rgba(218,221,228,245); }
    """


def _media_style_luxury() -> str:
    return """
        QFrame#luxury {
            background: qlineargradient(x1:0 y1:0, x2:1 y2:1,
                stop:0 #2b2530, stop:0.45 #221f27, stop:1 #15151b);
            border: 1px solid rgba(205,175,102,190);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: #d7bd74;
            font-size: 11px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: #fff2dc;
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(255,250,236,226);
            border: 1px solid rgba(207,177,105,148);
            border-radius: 18px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(75,62,42,208);
            border: 1px solid rgba(224,196,125,160);
            color: rgba(255,246,224,240);
            min-width: 30px; min-height: 30px;
            border-radius: 14px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: qlineargradient(x1:0 y1:0, x2:1 y2:1,
                stop:0 #f4d57e, stop:1 #c99945);
            border: 1px solid rgba(255,249,224,220);
            border-radius: 22px;
        }
        QPushButton:hover { background: rgba(255,255,247,248); border-color: rgba(232,205,136,210); }
        QPushButton:pressed { background: rgba(232,217,183,245); }
    """


def _media_style_ghost_acrylic() -> str:
    return """
        QFrame#ghost_acrylic {
            background: transparent;
            border: none;
        }
        QFrame#ghost_acrylic[hover="true"] {
            background: transparent;
            border: none;
        }
        QLabel#mediaAppLabel {
            color: rgba(252,248,255,242);
            font-size: 11px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(255,255,255,248);
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(255,255,255,190);
            border: 1px solid rgba(255,255,255,138);
            border-radius: 18px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(255,255,255,132);
            border: 1px solid rgba(255,255,255,115);
            border-radius: 14px;
            min-width: 30px; min-height: 30px;
            color: rgba(255,255,255,236);
            font-size: 13px;
            font-weight: 700;
        }
        QFrame#ghost_acrylic[hover="true"] QPushButton {
            background: rgba(255,255,255,224);
            border: 1px solid rgba(255,255,255,188);
        }
        QFrame#ghost_acrylic[hover="true"] QPushButton#mediaStyleButton {
            background: rgba(255,255,255,170);
            border: 1px solid rgba(255,255,255,176);
        }
        QPushButton#mediaPlayButton {
            background: qlineargradient(x1:0 y1:0, x2:1 y2:1,
                stop:0 rgba(255,151,210,250),
                stop:1 rgba(255,94,168,250));
            border: 1px solid rgba(255,241,248,220);
            min-width: 0px; min-height: 0px;
            border-radius: 22px;
        }
        QFrame#ghost_acrylic[hover="true"] QPushButton#mediaPlayButton {
            background: qlineargradient(x1:0 y1:0, x2:1 y2:1,
                stop:0 rgba(255,182,223,252),
                stop:1 rgba(255,116,181,252));
        }
        QPushButton:hover { background: rgba(255,255,255,228); }
        QPushButton:pressed { background: rgba(228,231,238,245); }
    """


def _media_style_stealth_acrylic() -> str:
    return """
        QFrame#stealth_acrylic {
            background: transparent;
            border: none;
        }
        QLabel#mediaAppLabel {
            color: rgba(255,255,255,156);
            font-size: 11px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(255,255,255,162);
            font-size: 12px;
            font-weight: 600;
        }
        QFrame#stealth_acrylic[hover="true"] QLabel#mediaAppLabel {
            color: rgba(255,255,255,242);
        }
        QFrame#stealth_acrylic[hover="true"] QLabel#mediaTrackLabel {
            color: rgba(255,255,255,248);
        }
        QPushButton {
            background: rgba(255,255,255,96);
            border: 1px solid rgba(255,255,255,62);
            border-radius: 18px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(32,32,38,92);
            border: 1px solid rgba(255,255,255,52);
            color: rgba(255,255,255,190);
            font-size: 13px;
            font-weight: 700;
            min-width: 30px; min-height: 30px;
            border-radius: 14px;
        }
        QPushButton#mediaPlayButton {
            background: rgba(255,255,255,130);
            border: 1px solid rgba(255,255,255,76);
            border-radius: 22px;
        }
        QFrame#stealth_acrylic[hover="true"] QPushButton {
            background: rgba(255,255,255,226);
            border: 1px solid rgba(255,255,255,160);
        }
        QFrame#stealth_acrylic[hover="true"] QPushButton#mediaStyleButton {
            background: rgba(48,48,58,188);
            color: rgba(255,255,255,242);
            border: 1px solid rgba(255,255,255,134);
        }
        QFrame#stealth_acrylic[hover="true"] QPushButton#mediaPlayButton {
            background: qlineargradient(x1:0 y1:0, x2:1 y2:1,
                stop:0 rgba(255,151,210,245),
                stop:1 rgba(255,94,168,245));
            border: 1px solid rgba(255,241,248,210);
        }
        QPushButton:hover { background: rgba(255,255,255,245); }
        QPushButton:pressed { background: rgba(228,231,238,245); }
    """


_MEDIA_ICON_CACHE: dict[str, QIcon] = {}


def _center_icon_path(path: QPainterPath, size: int = 32) -> QPainterPath:
    bounds = path.boundingRect()
    target = QRectF(0, 0, size, size).center()
    offset_x = target.x() - bounds.center().x()
    offset_y = target.y() - bounds.center().y()
    transform = QTransform()
    transform.translate(offset_x, offset_y)
    return transform.map(path)


def _next_icon_path() -> QPainterPath:
    path = QPainterPath()
    path.addPolygon(QPolygon([QPoint(6, 7), QPoint(17, 16), QPoint(6, 25)]))
    path.addRoundedRect(QRectF(19, 7, 3, 18), 1.2, 1.2)
    return path


def _previous_icon_path() -> QPainterPath:
    transform = QTransform()
    transform.translate(32, 0)
    transform.scale(-1, 1)
    return transform.map(_next_icon_path())


def _play_icon_path() -> QPainterPath:
    path = QPainterPath()
    path.addPolygon(QPolygon([QPoint(8, 6), QPoint(22, 16), QPoint(8, 26)]))
    return path


def _pause_icon_path() -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(8, 6, 5, 20), 1.4, 1.4)
    path.addRoundedRect(QRectF(19, 6, 5, 20), 1.4, 1.4)
    return path


def _media_icon(name: str) -> QIcon:
    name = str(name or "").strip().lower()
    if name in _MEDIA_ICON_CACHE:
        return _MEDIA_ICON_CACHE[name]

    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(34, 34, 42, 235))

    if name == "previous":
        path = _previous_icon_path()
    elif name == "next":
        path = _next_icon_path()
    elif name == "pause":
        path = _pause_icon_path()
    else:
        path = _play_icon_path()
    painter.drawPath(_center_icon_path(path))

    painter.end()
    icon = QIcon(pixmap)
    _MEDIA_ICON_CACHE[name] = icon
    return icon


class _MediaControlButton(QPushButton):
    def __init__(self, icon_name: str, *, primary: bool = False, parent=None):
        super().__init__(parent)
        self._media_style = "ghost_acrylic"
        self._primary = primary
        self.setIcon(_media_icon(icon_name))
        self.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_media_button_size(1, 1)

    def set_media_button_size(self, width: int, height: int):
        self.setFixedSize(width, height)
        self.setMinimumSize(width, height)
        self.setMaximumSize(width, height)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
                min-width: {width}px;
                min-height: {height}px;
                max-width: {width}px;
                max-height: {height}px;
                line-height: 0px;
            }}
        """)

    def set_media_style(self, style: str):
        self._media_style = str(style or "").strip().lower()
        self.update()

    def _colors(self):
        style = self._media_style
        if self._primary:
            if style == "cyber":
                return QColor("#7efff2"), QColor("#57a5ff"), QColor(231, 255, 255, 220)
            if style == "luxury":
                return QColor("#f4d57e"), QColor("#c99945"), QColor(255, 249, 224, 220)
            if style == "minimal":
                return QColor(255, 255, 255, 238), QColor(224, 228, 236, 238), QColor(255, 255, 255, 150)
            return QColor("#ff8cc8"), QColor("#ef4d9b"), QColor(255, 255, 255, 210)

        if style == "cyber":
            return QColor(232, 253, 255, 228), QColor(202, 242, 247, 228), QColor(75, 225, 232, 160)
        if style == "luxury":
            return QColor(255, 250, 236, 230), QColor(239, 224, 188, 230), QColor(207, 177, 105, 160)
        if style == "minimal":
            return QColor(246, 247, 250, 226), QColor(220, 224, 232, 226), QColor(255, 255, 255, 120)
        if style == "stealth_acrylic":
            return QColor(255, 255, 255, 146), QColor(228, 231, 238, 146), QColor(255, 255, 255, 96)
        return QColor(255, 255, 255, 226), QColor(228, 231, 238, 226), QColor(255, 255, 255, 150)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        top, bottom, border = self._colors()
        if self.isDown():
            top = top.darker(108)
            bottom = bottom.darker(112)
        elif self.underMouse():
            top = top.lighter(106)
            bottom = bottom.lighter(105)

        rect = self.rect().adjusted(1, 1, -1, -1)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(QBrush(gradient))
        radius = min(rect.width(), rect.height()) / 2
        painter.drawRoundedRect(rect, radius, radius)

        pixmap = self.icon().pixmap(self.iconSize())
        x = (self.width() - pixmap.width()) // 2
        y = (self.height() - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)

    def visible_button_rect(self) -> QRect:
        return self.rect().adjusted(1, 1, -1, -1)

    def visible_circle_rect(self) -> QRect:
        return self.visible_button_rect()


class MediaRadialItem(QFrame):
    """Media control card for the radial menu, replacing standalone overlay.

    Five visual styles: cute, cyber, minimal, luxury, ghost_acrylic.
    Ghost acrylic is the default — low presence, high visibility on hover.
    """

    command_requested = Signal(str)
    style_selected = Signal(str)

    VALID_STYLES = frozenset({
        "cute",
        "cyber",
        "minimal",
        "luxury",
        "ghost_acrylic",
        "stealth_acrylic",
    })

    def __init__(self, style: str = "ghost_acrylic", parent=None):
        super().__init__(parent)
        self._style = "ghost_acrylic"
        self._snapshot = None
        self._hover = False
        self._debug_overlay = False

        self.setObjectName("ghost_acrylic")
        self.setFixedSize(MEDIA_CARD_WIDTH, MEDIA_CARD_HEIGHT)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.98)
        self.setGraphicsEffect(self._opacity_effect)

        self._app_label = QLabel("No media", self)
        self._app_label.setObjectName("mediaAppLabel")
        self._style_menu_button = QPushButton("...", self)
        self._style_menu_button.setObjectName("mediaStyleButton")
        self._style_menu_button.setFixedSize(MEDIA_MENU_SIZE, MEDIA_MENU_SIZE)
        self._style_menu_button.setContentsMargins(0, 0, 0, 0)
        self._style_menu_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._style_menu_button.clicked.connect(self._show_style_menu)

        self._track_label = QLabel("", self)
        self._track_label.setObjectName("mediaTrackLabel")
        self._track_label.setWordWrap(True)
        self._track_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._track_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._controls_widget = QWidget(self)
        self._controls_widget.setObjectName("mediaControls")
        self._controls_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._controls_widget.setContentsMargins(0, 0, 0, 0)
        self._controls_widget.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._controls_layout = QHBoxLayout(self._controls_widget)
        self._controls_layout.setContentsMargins(0, 0, 0, 0)
        self._controls_layout.setSpacing(MEDIA_CONTROL_GAP)
        self._controls_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._prev_btn = self._mk_btn(
            "previous",
            MEDIA_CONTROL_SECONDARY_SIZE,
            MEDIA_CONTROL_SECONDARY_HEIGHT,
            15,
        )
        self._play_btn = self._mk_btn(
            "play",
            MEDIA_CONTROL_PRIMARY_SIZE,
            MEDIA_CONTROL_PRIMARY_HEIGHT,
            18,
            command="play_pause",
        )
        self._play_btn.setObjectName("mediaPlayButton")
        self._next_btn = self._mk_btn(
            "next",
            MEDIA_CONTROL_SECONDARY_SIZE,
            MEDIA_CONTROL_SECONDARY_HEIGHT,
            15,
        )
        self._controls_layout.addWidget(self._prev_btn)
        self._controls_layout.addWidget(self._play_btn)
        self._controls_layout.addWidget(self._next_btn)

        self._layout_children()
        self.set_style(style)

    def _mk_btn(self, icon_name: str, width: int, height: int, icon_size: int,
                command: str | None = None) -> QPushButton:
        btn = _MediaControlButton(
            icon_name,
            primary=(command == "play_pause"),
            parent=self._controls_widget,
        )
        btn.set_media_button_size(width, height)
        btn.setIconSize(QSize(icon_size, icon_size))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        command = command or icon_name
        btn.clicked.connect(lambda _c=False, c=command: self.command_requested.emit(c))
        return btn

    def _panel_rect(self) -> QRect:
        return self.rect().adjusted(
            MEDIA_PANEL_INSET,
            MEDIA_PANEL_INSET,
            -MEDIA_PANEL_INSET,
            -MEDIA_PANEL_INSET,
        )

    def set_debug_overlay_enabled(self, enabled: bool):
        self._debug_overlay = bool(enabled)
        self.update()

    def layout_debug_metrics(self) -> dict[str, object]:
        margins = self._controls_layout.contentsMargins()
        return {
            "widget_size": (self.width(), self.height()),
            "widget_rect": (
                self.rect().x(),
                self.rect().y(),
                self.rect().width(),
                self.rect().height(),
            ),
            "panel_rect": (
                self._panel_rect().x(),
                self._panel_rect().y(),
                self._panel_rect().width(),
                self._panel_rect().height(),
            ),
            "controls_geometry": (
                self._controls_widget.geometry().x(),
                self._controls_widget.geometry().y(),
                self._controls_widget.geometry().width(),
                self._controls_widget.geometry().height(),
            ),
            "controls_margins": (
                margins.left(),
                margins.top(),
                margins.right(),
                margins.bottom(),
            ),
            "controls_spacing": self._controls_layout.spacing(),
            "device_pixel_ratio": self.devicePixelRatioF(),
            "buttons": {
                name: {
                    "geometry": (
                        button.geometry().x(),
                        button.geometry().y(),
                        button.geometry().width(),
                        button.geometry().height(),
                    ),
                    "contents_rect": (
                        button.contentsRect().x(),
                        button.contentsRect().y(),
                        button.contentsRect().width(),
                        button.contentsRect().height(),
                    ),
                    "size_hint": (
                        button.sizeHint().width(),
                        button.sizeHint().height(),
                    ),
                    "minimum_size": (
                        button.minimumSize().width(),
                        button.minimumSize().height(),
                    ),
                    "maximum_size": (
                        button.maximumSize().width(),
                        button.maximumSize().height(),
                    ),
                }
                for name, button in (
                    ("previous", self._prev_btn),
                    ("play_pause", self._play_btn),
                    ("next", self._next_btn),
                )
            },
        }

    def _draw_debug_overlay(self, painter: QPainter):
        widget_rect = self.rect().adjusted(0, 0, -1, -1)
        panel_rect = self._panel_rect()
        controls_rect = self._controls_widget.geometry()

        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 70, 70, 230), 1))
        painter.drawRect(widget_rect)

        painter.setPen(QPen(QColor(80, 255, 120, 230), 1))
        painter.drawRect(panel_rect)
        panel_center_x = panel_rect.left() + panel_rect.width() / 2
        painter.drawLine(int(round(panel_center_x)), panel_rect.top(),
                         int(round(panel_center_x)), panel_rect.bottom())

        painter.setPen(QPen(QColor(80, 150, 255, 235), 1))
        painter.drawRect(controls_rect)
        controls_center_x = controls_rect.left() + controls_rect.width() / 2
        painter.drawLine(int(round(controls_center_x)), controls_rect.top(),
                         int(round(controls_center_x)), controls_rect.bottom())

        for button in (self._prev_btn, self._play_btn, self._next_btn):
            button_rect = QRect(
                self._controls_widget.x() + button.x(),
                self._controls_widget.y() + button.y(),
                button.width(),
                button.height(),
            )
            circle_rect = button.visible_circle_rect().translated(button_rect.topLeft())
            painter.setPen(QPen(QColor(255, 224, 75, 235), 1))
            painter.drawRect(button_rect)
            painter.setPen(QPen(QColor(220, 80, 255, 235), 1))
            painter.drawEllipse(circle_rect)
        painter.restore()

    def _layout_children(self):
        panel_rect = self._panel_rect()
        self._style_menu_button.move(
            panel_rect.right() + 1 - MEDIA_MENU_RIGHT_MARGIN - self._style_menu_button.width(),
            panel_rect.top() + MEDIA_MENU_TOP_MARGIN,
        )
        self._app_label.setGeometry(
            panel_rect.left() + MEDIA_TITLE_LEFT_MARGIN,
            panel_rect.top() + MEDIA_TITLE_TOP_MARGIN,
            panel_rect.width() - MEDIA_TITLE_LEFT_MARGIN * 2 - MEDIA_MENU_SIZE,
            20,
        )
        self._track_label.setGeometry(
            panel_rect.left() + MEDIA_TITLE_LEFT_MARGIN,
            panel_rect.top() + MEDIA_TITLE_TOP_MARGIN + MEDIA_TRACK_TOP_OFFSET,
            panel_rect.width() - MEDIA_TITLE_LEFT_MARGIN * 2,
            MEDIA_TRACK_HEIGHT,
        )

        spacing = self._controls_layout.spacing()
        group_w = self._prev_btn.width() + self._play_btn.width() + self._next_btn.width() + spacing * 2
        group_h = max(self._prev_btn.height(), self._play_btn.height(), self._next_btn.height())
        self._controls_widget.setFixedSize(group_w, group_h)
        group_x = round(panel_rect.left() + (panel_rect.width() - group_w) / 2)
        group_y = panel_rect.bottom() + 1 - MEDIA_CONTROL_BOTTOM_MARGIN - group_h
        self._controls_widget.setGeometry(group_x, group_y, group_w, group_h)
        self._controls_layout.activate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_children()

    # -- public API --

    def set_style(self, style: str):
        style = str(style or "").strip().lower()
        if style not in self.VALID_STYLES:
            style = "ghost_acrylic"
        self._style = style
        self.setObjectName(style)
        sheet = STYLE_SHEET_CACHE.get(style)
        if sheet is None:
            sheet = _build_media_style_sheet(style)
            STYLE_SHEET_CACHE[style] = sheet
        self.setStyleSheet(sheet)
        for button in (self._prev_btn, self._play_btn, self._next_btn):
            if isinstance(button, _MediaControlButton):
                button.set_media_style(style)
        self._sync_hover_style()
        self._layout_children()
        self.update()

    def _show_style_menu(self):
        menu = QMenu(self)
        menu.setObjectName("mediaStyleMenu")
        labels = {
            "cute": "Cute",
            "cyber": "Cyber",
            "minimal": "Minimal",
            "luxury": "Luxury",
            "ghost_acrylic": "Ghost Acrylic",
            "stealth_acrylic": "Stealth Acrylic",
        }
        for style in ("cute", "cyber", "minimal", "luxury", "ghost_acrylic", "stealth_acrylic"):
            action = menu.addAction(labels[style])
            action.setCheckable(True)
            action.setChecked(style == self._style)
            action.triggered.connect(lambda _checked=False, s=style: self._select_style(s))
        menu.popup(self._style_menu_button.mapToGlobal(self._style_menu_button.rect().bottomRight()))

    def _select_style(self, style: str):
        self.set_style(style)
        self.style_selected.emit(self._style)

    @property
    def style_name(self) -> str:
        return self._style

    def set_snapshot(self, snapshot):
        """Bind a MediaSessionSnapshot (or None for empty state)."""
        self._snapshot = snapshot
        if snapshot is None:
            self._app_label.setText("No media")
            self._track_label.setText("No active playback")
            self._track_label.setToolTip("")
            self._play_btn.setIcon(_media_icon("play"))
            return
        from media_session_manager import display_app_name, format_track_line

        app = display_app_name(snapshot.app_id)
        track = format_track_line(snapshot)
        self._app_label.setText(app)
        metrics = self._track_label.fontMetrics()
        text_width = max(160, self._track_label.width() - 4)
        elided = metrics.elidedText(track, Qt.TextElideMode.ElideRight, text_width)
        self._track_label.setText(elided)
        self._track_label.setToolTip(track)
        self._play_btn.setIcon(
            _media_icon("pause" if snapshot.playback_status == "playing" else "play")
        )

    # -- hover for acrylic styles --

    def _sync_hover_style(self):
        if self._style in {"ghost_acrylic", "stealth_acrylic"}:
            default_opacity = 0.52 if self._style == "stealth_acrylic" else 0.98
            self._opacity_effect.setOpacity(1.0 if self._hover else default_opacity)
            self.setProperty("hover", "true" if self._hover else "false")
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            self._opacity_effect.setOpacity(1.0)
            self.setProperty("hover", "false")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        shadow_rect = self._panel_rect().adjusted(2, 10, -2, 10)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._style == "stealth_acrylic" and not self._hover:
            painter.setBrush(QColor(0, 0, 0, 18))
        else:
            painter.setBrush(QColor(15, 23, 42, 72 if self._hover else 54))
        painter.drawRoundedRect(shadow_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)

        panel_rect = self._panel_rect()
        gradient = QLinearGradient(panel_rect.topLeft(), panel_rect.bottomRight())
        border = QColor(255, 255, 255, 130)
        highlight_alpha = 20

        if self._style == "cute":
            gradient.setColorAt(0.0, QColor(255, 244, 250, 250))
            gradient.setColorAt(1.0, QColor(255, 192, 216, 250))
            border = QColor(255, 124, 175, 210)
            highlight_alpha = 34
        elif self._style == "cyber":
            gradient.setColorAt(0.0, QColor(21, 25, 37, 250))
            gradient.setColorAt(1.0, QColor(6, 18, 27, 252))
            border = QColor(88, 244, 240, 220)
            highlight_alpha = 18
        elif self._style == "minimal":
            gradient.setColorAt(0.0, QColor(58, 60, 69, 248))
            gradient.setColorAt(1.0, QColor(32, 35, 43, 250))
            border = QColor(255, 255, 255, 42)
            highlight_alpha = 14
        elif self._style == "luxury":
            gradient.setColorAt(0.0, QColor(44, 38, 48, 250))
            gradient.setColorAt(1.0, QColor(21, 21, 27, 252))
            border = QColor(216, 185, 107, 220)
            highlight_alpha = 20
        elif self._style == "stealth_acrylic" and not self._hover:
            gradient.setColorAt(0.0, QColor(42, 42, 54, 96))
            gradient.setColorAt(1.0, QColor(22, 24, 32, 106))
            border = QColor(255, 255, 255, 42)
            highlight_alpha = 12
        elif self._hover:
            gradient.setColorAt(0.0, QColor(76, 74, 92, 244))
            gradient.setColorAt(1.0, QColor(35, 38, 48, 248))
            border = QColor(255, 255, 255, 196)
            highlight_alpha = 34
        else:
            gradient.setColorAt(0.0, QColor(76, 74, 92, 240))
            gradient.setColorAt(1.0, QColor(35, 38, 48, 246))
            border = QColor(255, 255, 255, 148)
            highlight_alpha = 20

        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(border, 1.2))
        painter.drawRoundedRect(panel_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(panel_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)
        painter.save()
        painter.setClipPath(clip_path)
        if self._style == "cute":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 86))
            painter.drawEllipse(panel_rect.right() - 54, panel_rect.top() + 16, 34, 20)
            painter.setBrush(QColor(255, 112, 178, 50))
            painter.drawEllipse(panel_rect.left() + 18, panel_rect.top() + 18, 46, 46)
            painter.setBrush(QColor(255, 112, 178, 34))
            painter.drawEllipse(panel_rect.right() - 72, panel_rect.bottom() - 54, 58, 58)
        elif self._style == "cyber":
            painter.setPen(QPen(QColor(88, 244, 240, 46), 1))
            grid = 18
            x = panel_rect.left()
            while x < panel_rect.right():
                painter.drawLine(x, panel_rect.top(), x, panel_rect.bottom())
                x += grid
            painter.setPen(QPen(QColor(88, 244, 240, 31), 1))
            y = panel_rect.top()
            while y < panel_rect.bottom():
                painter.drawLine(panel_rect.left(), y, panel_rect.right(), y)
                y += grid
            scan_y = panel_rect.top() + int(panel_rect.height() * 0.48)
            scan = QLinearGradient(panel_rect.left(), scan_y,
                                   panel_rect.right(), scan_y + 8)
            scan.setColorAt(0.0, QColor(102, 255, 244, 0))
            scan.setColorAt(0.36, QColor(102, 255, 244, 165))
            scan.setColorAt(0.6, QColor(255, 93, 183, 150))
            scan.setColorAt(1.0, QColor(102, 255, 244, 0))
            painter.setPen(QPen(QBrush(scan), 2.0))
            painter.drawLine(panel_rect.left() - 36, scan_y + 16,
                             panel_rect.right() + 36, scan_y - 14)
        elif self._style == "luxury":
            inner = panel_rect.adjusted(11, 10, -11, -10)
            painter.setPen(QPen(QColor(216, 185, 107, 82), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(inner, 14, 14)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(216, 185, 107, 36))
            painter.drawEllipse(panel_rect.left() + 20, panel_rect.top() + 14, 42, 42)
        painter.restore()

        highlight_rect = panel_rect.adjusted(10, 8, -10, -panel_rect.height() + 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, highlight_alpha))
        painter.drawRoundedRect(highlight_rect, 6, 6)
        if self._debug_overlay:
            self._draw_debug_overlay(painter)

    def enterEvent(self, event):
        self._hover = True
        self._sync_hover_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._sync_hover_style()
        super().leaveEvent(event)


# -- style sheet cache and builder --

STYLE_SHEET_CACHE: dict[str, str] = {}

_STYLE_FUNCTIONS = {
    "cute": _media_style_cute,
    "cyber": _media_style_cyber,
    "minimal": _media_style_minimal,
    "luxury": _media_style_luxury,
    "ghost_acrylic": _media_style_ghost_acrylic,
    "stealth_acrylic": _media_style_stealth_acrylic,
}


def _build_media_style_sheet(style: str) -> str:
    func = _STYLE_FUNCTIONS.get(style)
    if func is None:
        return _media_style_ghost_acrylic()
    return func()


@dataclass
class _ItemData:
    widget: QWidget
    start_offset: QPoint
    end_offset: QPoint
    opacity_effect: QGraphicsOpacityEffect
    is_media: bool = False


class RadialMenu(QWidget):
    closed = Signal()
    lock_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if sys.platform.startswith("linux"):
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(False)

        self._items: list[_ItemData] = []
        self._is_showing = False
        self._center = QPoint(0, 0)
        self._anchor_local = QPoint(0, 0)
        self._radius = 110
        self._anim_group = None
        self._fps = 120
        self._locked = False
        self._center_hover = False
        self._center_opacity = 1.0
        self._center_scale = 1.0
        self._center_anim_value = 1.0
        self._lock_anim = None
        self._paint_prewarmed = False
        self._ignore_outside_click_until_release = False
        self._outside_click_timer = QTimer(self)
        self._outside_click_timer.setInterval(25)
        self._outside_click_timer.timeout.connect(self._check_outside_click)

        self.setMouseTracking(True)

    def _menu_center(self) -> QPoint:
        if self._anchor_local.isNull():
            return QPoint(self.width() // 2, self.height() // 2)
        return self._anchor_local

    def nativeEvent(self, event_type, message):
        if os.name == "nt":
            try:
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_NCCALCSIZE:
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def _apply_windows_11_border_fix(self):
        if os.name != "nt" or _dwm_set_window_attribute is None:
            return
        hwnd = int(self.winId())
        if not hwnd:
            return
        for attr, value in (
            (DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND),
            (DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE),
        ):
            value_ref = ctypes.c_int(value)
            try:
                _dwm_set_window_attribute(
                    hwnd,
                    attr,
                    ctypes.byref(value_ref),
                    ctypes.sizeof(value_ref),
                )
            except Exception:
                pass
        if _set_window_pos is not None:
            _set_window_pos(
                hwnd,
                None,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_windows_11_border_fix()
        QTimer.singleShot(0, self._apply_windows_11_border_fix)
        if macos_patch is not None:
            QTimer.singleShot(0, self._apply_macos_window_polish)

    def _apply_macos_window_polish(self):
        if macos_patch is None:
            return
        macos_patch.set_window_no_shadow(self)
        # Use status-bar level so the menu stays above the floating pet window.
        macos_patch.set_window_level_above_menu_bar(self)

    def prepare_for_show(self):
        # Force native window creation during idle time so first popup stays responsive.
        self.winId()
        self._apply_windows_11_border_fix()
        if macos_patch is not None:
            self._apply_macos_window_polish()
        self._prewarm_paint_cache()

    def _media_item_size(self) -> QSize:
        for item in self._items:
            if item.is_media:
                return item.widget.size()
        return QSize(0, 0)

    def _menu_popup_size(self, has_media: bool) -> QSize:
        base_w = self._radius * 2 + 80 * 2
        base_h = self._radius * 2 + 80 * 2
        if not has_media:
            return QSize(base_w, base_h)

        media_size = self._media_item_size()
        return QSize(
            base_w + media_size.width() + 64,
            max(base_h + 40, media_size.height() + 56),
        )

    def _clamped_top_left(self, center: QPoint, size: QSize) -> QPoint:
        x = center.x() - size.width() // 2
        y = center.y() - size.height() // 2
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        if screen is None:
            return QPoint(x, y)

        available = screen.availableGeometry()
        margin = 4
        max_x = available.right() - size.width() + 1 - margin
        max_y = available.bottom() - size.height() + 1 - margin
        x = max(available.left() + margin, min(x, max_x))
        y = max(available.top() + margin, min(y, max_y))
        return QPoint(x, y)

    def _prewarm_paint_cache(self):
        if self._paint_prewarmed:
            return

        has_media = any(item.is_media for item in self._items)
        popup_size = self._menu_popup_size(has_media)
        total_w = popup_size.width()
        total_h = popup_size.height()
        if self.width() != total_w or self.height() != total_h:
            self.resize(total_w, total_h)
        self._anchor_local = QPoint(total_w // 2, total_h // 2)

        # Windows can stall the first time Qt resolves emoji fallback fonts and
        # translucent gradients. Render once while hidden so right-click only shows.
        self._set_center_reveal_value(1.0)
        menu_pixmap = QPixmap(total_w, total_h)
        menu_pixmap.fill(Qt.GlobalColor.transparent)
        self.render(menu_pixmap)

        for item in self._items:
            item_pixmap = QPixmap(item.widget.size())
            item_pixmap.fill(Qt.GlobalColor.transparent)
            item.widget.render(item_pixmap)

        self._paint_prewarmed = True

    @property
    def locked(self):
        return self._locked

    def set_locked(self, locked: bool):
        self._locked = locked
        self._center_opacity = 1.0
        self._center_scale = 1.0
        self._center_anim_value = 1.0
        self.update()

    def _set_center_reveal_value(self, value: float):
        self._center_anim_value = value
        self._center_opacity = value
        self._center_scale = 0.72 + 0.28 * value
        self.update()

    def _set_center_anim_value(self, value: float):
        if value < 0.5:
            t = value / 0.5
            self._center_opacity = 1.0 - t
            self._center_scale = 1.0 - 0.16 * t
        else:
            t = (value - 0.5) / 0.5
            self._center_opacity = t
            self._center_scale = 0.84 + 0.16 * t
        self.update()

    def _toggle_locked(self):
        if self._lock_anim and self._lock_anim.state() == QVariantAnimation.State.Running:
            return

        anim = QVariantAnimation(self)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        switched = {"done": False}

        def update(value):
            if value >= 0.5 and not switched["done"]:
                switched["done"] = True
                self._locked = not self._locked
                self.lock_toggled.emit(self._locked)
            self._set_center_anim_value(float(value))

        anim.valueChanged.connect(update)
        anim.finished.connect(lambda: self._set_center_anim_value(1.0))
        self._lock_anim = anim
        anim.start()

    def set_animation_fps(self, fps: int):
        self._fps = max(30, min(fps, 240))

    def _show_duration(self):
        return max(150, int(300 * 120 / self._fps))

    def _hide_duration(self):
        return max(100, int(200 * 120 / self._fps))

    def add_item(self, icon: str, label: str, color: QColor,
                 on_click: Callable, glyph: str = "", enabled: bool = True):
        w = RadialMenuItem(icon, label, color, glyph=glyph, enabled=enabled, parent=self)
        w.clicked.connect(on_click)
        w.clicked.connect(self._on_item_clicked)
        w.hide()

        opacity = QGraphicsOpacityEffect(w)
        opacity.setOpacity(0.0)
        w.setGraphicsEffect(opacity)

        self._items.append(_ItemData(
            widget=w,
            start_offset=QPoint(0, 0),
            end_offset=QPoint(0, 0),
            opacity_effect=opacity,
        ))

    def add_spacer(self):
        w = QWidget(self)
        w.setFixedSize(80, 80)
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        w.hide()

        opacity = QGraphicsOpacityEffect(w)
        opacity.setOpacity(0.0)
        w.setGraphicsEffect(opacity)

        self._items.append(_ItemData(
            widget=w,
            start_offset=QPoint(0, 0),
            end_offset=QPoint(0, 0),
            opacity_effect=opacity,
        ))

    def add_media_item(self, style: str = "ghost_acrylic") -> MediaRadialItem:
        """Add a media control card at the leftmost position of the radial menu."""
        w = MediaRadialItem(style=style, parent=self)
        w.command_requested.connect(self._on_item_clicked)
        w.hide()

        opacity = QGraphicsOpacityEffect(w)
        opacity.setOpacity(0.0)
        w.setGraphicsEffect(opacity)

        self._items.append(_ItemData(
            widget=w,
            start_offset=QPoint(0, 0),
            end_offset=QPoint(0, 0),
            opacity_effect=opacity,
            is_media=True,
        ))
        return w

    def update_item(self, index: int, *, label: str | None = None,
                    glyph: str | None = None, enabled: bool | None = None):
        if index < 0 or index >= len(self._items):
            return
        widget = self._items[index].widget
        if isinstance(widget, RadialMenuItem):
            if label is not None:
                widget.set_label(label)
            if glyph is not None:
                widget.set_glyph(glyph)
            if enabled is not None:
                widget.set_enabled_state(enabled)

    def show_at(self, center: QPoint):
        if self._is_showing:
            return

        n = len(self._items)
        if n == 0:
            return

        has_media = any(item.is_media for item in self._items)
        self._center = center
        self._is_showing = True
        self._ignore_outside_click_until_release = self._mouse_buttons_pressed()
        self._set_center_reveal_value(0.0)

        popup_size = self._menu_popup_size(has_media)
        total_w = popup_size.width()
        total_h = popup_size.height()
        top_left = self._clamped_top_left(center, popup_size)

        self.setGeometry(top_left.x(), top_left.y(), total_w, total_h)

        self._anchor_local = center - top_left
        cx = self._anchor_local.x()
        cy = self._anchor_local.y()

        if has_media:
            self._layout_with_media(cx, cy)
        else:
            self._layout_circle(cx, cy, range(n))

        for item in self._items:
            item.widget.show()

        self.show()
        if sys.platform.startswith("linux"):
            self.raise_()
            self.activateWindow()
            QTimer.singleShot(0, self.raise_)
            QTimer.singleShot(0, self.activateWindow)
        else:
            self.setFocus()
        self._play_show_animation()
        self._outside_click_timer.start()

    def _layout_circle(self, cx: int, cy: int, indices):
        """Position items indexed by *indices* evenly around a circle."""
        n = len(indices)
        for j, i in enumerate(indices):
            item = self._items[i]
            angle = -math.pi / 2 + (2 * math.pi * j / n)
            dx = int(self._radius * math.cos(angle))
            dy = int(self._radius * math.sin(angle))
            item.end_offset = QPoint(dx, dy)
            item.start_offset = QPoint(0, 0)

            item.widget.move(
                cx - item.widget.width() // 2,
                cy - item.widget.height() // 2,
            )

    def _layout_with_media(self, cx: int, cy: int):
        """Layout: media item on the right, actions in a left-side crescent."""
        media_idx = None
        other_indices = []
        for i, item in enumerate(self._items):
            if item.is_media:
                media_idx = i
            else:
                other_indices.append(i)

        # Media item: centered vertically, shifted left
        if media_idx is not None:
            media = self._items[media_idx]
            mw = media.widget.width()
            mh = media.widget.height()
            # Place media item left of the circle center
            start_x = cx - mw // 2
            right_x = min(self.width() - mw - 16, cx + self._radius // 2 + 18)
            media.end_offset = QPoint(right_x - start_x, 0)
            media.start_offset = QPoint(0, 0)
            media.widget.move(start_x, cy - mh // 2)

        # Other items circle on the right side (skip left quadrant, angles -π/2 ± small)
        if other_indices:
            self._layout_left_crescent(cx, cy, other_indices)

    def _layout_left_crescent(self, cx: int, cy: int, indices):
        """Position action items in a left crescent that avoids the pet core."""
        n = len(indices)
        if n == 0:
            return
        if n == 1:
            degrees = [180]
        else:
            degrees = [-70 + 140 * j / (n - 1) for j in range(n)]

        x_radius = self._radius + 58
        y_radius = self._radius + 8
        for deg, i in zip(degrees, indices):
            item = self._items[i]
            angle = math.pi + math.radians(deg)
            dx = int(x_radius * math.cos(angle))
            dy = int(y_radius * math.sin(angle))

            start_x = cx - item.widget.width() // 2
            start_y = cy - item.widget.height() // 2
            target_x = max(16, cx + dx - item.widget.width() // 2)
            target_y = max(
                16,
                min(self.height() - item.widget.height() - 16,
                    cy + dy - item.widget.height() // 2),
            )
            item.end_offset = QPoint(target_x - start_x, target_y - start_y)
            item.start_offset = QPoint(0, 0)
            item.widget.move(start_x, start_y)

    @staticmethod
    def _mouse_buttons_pressed() -> bool:
        if _get_async_key_state is not None:
            return any(
                bool(_get_async_key_state(button) & 0x8000)
                for button in (VK_LBUTTON, VK_RBUTTON, VK_MBUTTON)
            )
        return bool(QGuiApplication.mouseButtons())

    def _check_outside_click(self):
        if not self._is_showing or not self.isVisible():
            self._outside_click_timer.stop()
            return
        buttons_pressed = self._mouse_buttons_pressed()
        if not buttons_pressed:
            self._ignore_outside_click_until_release = False
            return
        if self._ignore_outside_click_until_release:
            return
        if not self.geometry().contains(QCursor.pos()):
            self.dismiss()

    def _play_show_animation(self):
        group = QParallelAnimationGroup(self)
        for item in self._items:
            anim = QPropertyAnimation(item.widget, b"pos")
            start_pos = item.widget.pos() + item.start_offset
            end_pos = item.widget.pos() + item.end_offset
            anim.setStartValue(start_pos)
            anim.setEndValue(end_pos)
            anim.setDuration(self._show_duration())
            anim.setEasingCurve(QEasingCurve.Type.OutBack)
            group.addAnimation(anim)

            op_anim = QPropertyAnimation(item.opacity_effect, b"opacity")
            op_anim.setStartValue(0.0)
            op_anim.setEndValue(1.0)
            op_anim.setDuration(max(120, self._show_duration() - 50))
            group.addAnimation(op_anim)

        center_anim = QVariantAnimation(self)
        center_anim.setStartValue(0.0)
        center_anim.setEndValue(1.0)
        center_anim.setDuration(max(140, self._show_duration() - 30))
        center_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        center_anim.valueChanged.connect(lambda v: self._set_center_reveal_value(float(v)))
        group.addAnimation(center_anim)

        self._anim_group = group
        group.start()

    def _play_hide_animation(self):
        group = QParallelAnimationGroup(self)
        for item in self._items:
            anim = QPropertyAnimation(item.widget, b"pos")
            start_pos = item.widget.pos()
            end_pos = item.widget.pos() - item.end_offset
            anim.setStartValue(start_pos)
            anim.setEndValue(end_pos)
            anim.setDuration(self._hide_duration())
            anim.setEasingCurve(QEasingCurve.Type.InBack)
            group.addAnimation(anim)

            op_anim = QPropertyAnimation(item.opacity_effect, b"opacity")
            op_anim.setStartValue(1.0)
            op_anim.setEndValue(0.0)
            op_anim.setDuration(max(80, self._hide_duration() - 50))
            group.addAnimation(op_anim)

        center_anim = QVariantAnimation(self)
        center_anim.setStartValue(self._center_anim_value)
        center_anim.setEndValue(0.0)
        center_anim.setDuration(max(90, self._hide_duration() - 20))
        center_anim.setEasingCurve(QEasingCurve.Type.InBack)
        center_anim.valueChanged.connect(lambda v: self._set_center_reveal_value(float(v)))
        group.addAnimation(center_anim)

        group.finished.connect(self._on_hide_finished)
        self._anim_group = group
        group.start()

    def _on_hide_finished(self):
        self._outside_click_timer.stop()
        self._is_showing = False
        self.hide()
        self.closed.emit()

    def _on_item_clicked(self):
        self.dismiss()

    def dismiss(self):
        self._outside_click_timer.stop()
        if self._is_showing:
            if self._anim_group and self._anim_group.state() == QPropertyAnimation.State.Running:
                self._anim_group.stop()
            self._play_hide_animation()
        else:
            self.hide()
            self.closed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        center = self._menu_center()
        cx = center.x()
        cy = center.y()
        dx = event.pos().x() - cx
        dy = event.pos().y() - cy
        dist = (dx * dx + dy * dy) ** 0.5
        was_hover = self._center_hover
        self._center_hover = dist < 40
        if was_hover != self._center_hover:
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        if any(item.widget.geometry().contains(event.pos()) for item in self._items):
            super().mousePressEvent(event)
            return

        center = self._menu_center()
        cx = center.x()
        cy = center.y()
        dx = event.pos().x() - cx
        dy = event.pos().y() - cy
        dist = (dx * dx + dy * dy) ** 0.5

        if dist < 40:
            self._toggle_locked()
        else:
            self.dismiss()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self._menu_center()
        cx = center.x()
        cy = center.y()
        rr = 30 * self._center_scale

        base = QColor("#3a3a3a") if self._center_hover else QColor("#2a2a2a")
        p.setOpacity(self._center_opacity)
        p.setPen(QPen(QColor("#555555"), 2))
        gradient = QRadialGradient(cx, cy - rr * 0.2, rr * 1.2)
        gradient.setColorAt(0, base.lighter(140))
        gradient.setColorAt(0.7, base)
        gradient.setColorAt(1, base.darker(140))
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPoint(int(cx), int(cy)), rr, rr)

        glyph = "\U0001F512" if self._locked else "\U0001F513"
        font = p.font()
        font.setPointSize(18)
        p.setFont(font)
        fm = QFontMetrics(font)
        g_w = fm.horizontalAdvance(glyph)
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(int(cx - g_w / 2), int(cy + 6), glyph)
        p.setOpacity(1.0)
