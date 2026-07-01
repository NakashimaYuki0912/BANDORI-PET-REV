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

MEDIA_CARD_WIDTH = 310
MEDIA_CARD_HEIGHT = 144
MEDIA_PANEL_INSET = 4
MEDIA_CARD_RADIUS = 18
MEDIA_CONTROL_SECONDARY_SIZE = 34
MEDIA_CONTROL_SECONDARY_HEIGHT = 26
MEDIA_CONTROL_PRIMARY_SIZE = 34
MEDIA_CONTROL_PRIMARY_HEIGHT = 26
MEDIA_CONTROL_GAP = 10
MEDIA_CONTROL_BOTTOM_MARGIN = 0  # vertically centered, not bottom-anchored
MEDIA_MENU_SIZE = 24
MEDIA_MENU_TOP_MARGIN = 10
MEDIA_MENU_RIGHT_MARGIN = 10
MEDIA_TITLE_LEFT_MARGIN = 14
MEDIA_TITLE_TOP_MARGIN = 14
MEDIA_TRACK_TOP_OFFSET = 32
MEDIA_TRACK_HEIGHT = 32

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

        color = self._color
        if not self._enabled:
            color = QColor(120, 120, 120)

        # Background: subtle translucent fill
        p.setPen(Qt.PenStyle.NoPen)
        bg = QColor(color)
        bg.setAlpha(50 if not self._hover else 75)
        p.setBrush(QBrush(bg))
        p.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r))

        # Border ring
        border = QColor(color)
        border.setAlpha(140 if not self._hover else 210)
        pen = QPen(border, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r))

        # Icon / glyph — top portion (upper ~55%)
        if self._icon and not self._icon.isNull():
            icon_size = int(r * 0.5)
            scaled = self._icon.scaled(
                icon_size, icon_size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            p.drawPixmap(int(cx - icon_size / 2), int(cy - icon_size / 2 - r * 0.18), scaled)
        elif self._glyph:
            font = p.font()
            font.setPointSize(20)
            p.setFont(font)
            glyph_color = QColor(color)
            glyph_color.setAlpha(210 if not self._hover else 240)
            p.setPen(glyph_color)
            # Top ~55% of the circle (ends at cy + r*0.10)
            glyph_rect = QRectF(cx - r * 0.8, cy - r * 0.45, r * 1.6, r * 0.55)
            p.drawText(glyph_rect, Qt.AlignmentFlag.AlignCenter, self._glyph)

        # Label — bottom portion (lower ~35%), no overlap with glyph
        font = p.font()
        font.setPointSize(9)
        font.setBold(False)
        p.setFont(font)
        label_color = QColor(255, 255, 255, 195 if not self._hover else 230)
        p.setPen(label_color)
        label_rect = QRectF(cx - r * 0.85, cy + r * 0.25, r * 1.7, r * 0.40)
        p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine, self._label)

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

def _media_style_aurora() -> str:
    """极光 — vertical flowing bands (green/teal/purple) with streak mask."""
    return """
        QFrame#aurora {
            background: transparent;
            border: 1px solid rgba(80,180,160,56);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(160,210,200,191);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(200,235,225,224);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(100,190,170,89);
            border: 1px solid rgba(100,200,170,38);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(100,180,160,26);
            border: 1px solid rgba(80,180,160,41);
            color: rgba(140,200,180,153);
            min-width: 24px; min-height: 24px;
            border-radius: 12px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: rgba(70,200,150,179);
            border: none;
            border-radius: 13px;
        }
        QPushButton:hover { background: rgba(120,210,185,128); }
        QPushButton:pressed { background: rgba(60,170,140,179); }
    """


def _media_style_neon() -> str:
    """霓虹脉冲 — scan-line grid + neon glow border."""
    return """
        QFrame#neon {
            background: transparent;
            border: 1px solid rgba(0,210,240,89);
            border-radius: 14px;
        }
        QLabel#mediaAppLabel {
            color: rgba(100,230,245,191);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(200,248,255,230);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(0,180,220,31);
            border: 1px solid rgba(0,200,230,46);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(0,180,210,26);
            border: 1px solid rgba(0,200,230,51);
            color: rgba(100,230,245,153);
            min-width: 24px; min-height: 24px;
            border-radius: 12px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: rgba(0,210,240,153);
            border: 1px solid rgba(150,240,255,64);
            border-radius: 13px;
        }
        QPushButton:hover { background: rgba(0,200,230,77); }
        QPushButton:pressed { background: rgba(0,160,200,128); }
    """


def _media_style_glass() -> str:
    """磨砂玻璃 — translucent layers with edge highlights."""
    return """
        QFrame#glass {
            background: transparent;
            border: 1px solid rgba(255,255,255,36);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(255,255,255,153);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(255,255,255,224);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(255,255,255,26);
            border: 1px solid rgba(255,255,255,26);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(255,255,255,20);
            color: rgba(255,255,255,128);
            min-width: 24px; min-height: 24px;
            border-radius: 12px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: rgba(255,255,255,46);
            border: 1px solid rgba(255,255,255,26);
            border-radius: 13px;
        }
        QPushButton:hover { background: rgba(255,255,255,64); }
        QPushButton:pressed { background: rgba(255,255,255,102); }
    """


def _media_style_velvet() -> str:
    """丝绒暗夜 — deep purple/gold gradient with inner border."""
    return """
        QFrame#velvet {
            background: transparent;
            border: 1px solid rgba(180,150,100,56);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(200,170,130,166);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(235,220,200,217);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(180,150,100,26);
            border: 1px solid rgba(180,150,100,31);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(180,150,100,26);
            border: 1px solid rgba(180,150,100,36);
            color: rgba(200,170,130,128);
            min-width: 24px; min-height: 24px;
            border-radius: 12px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: rgba(200,155,90,128);
            border: none;
            border-radius: 13px;
        }
        QPushButton:hover { background: rgba(200,170,120,64); }
        QPushButton:pressed { background: rgba(140,110,60,102); }
    """


def _media_style_prism() -> str:
    """全息幻彩 — iridescent multi-angle gradients with rainbow sheen."""
    return """
        QFrame#prism {
            background: transparent;
            border: 1px solid rgba(180,180,200,46);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(180,190,220,153);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(220,225,240,217);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(180,185,210,20);
            border: 1px solid rgba(180,185,210,26);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(255,255,255,15);
            border: 1px solid rgba(180,180,200,31);
            color: rgba(180,190,220,128);
            min-width: 24px; min-height: 24px;
            border-radius: 12px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: rgba(130,150,210,115);
            border: none;
            border-radius: 13px;
        }
        QPushButton:hover { background: rgba(255,255,255,51); }
        QPushButton:pressed { background: rgba(140,140,200,77); }
    """


def _media_style_blossom() -> str:
    """花漾粉 — light pink/white gradient with warm glow."""
    return """
        QFrame#blossom {
            background: transparent;
            border: 1px solid rgba(230,120,160,77);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: #b0496b;
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: #4a2535;
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(255,255,255,191);
            border: 1px solid rgba(220,140,170,51);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(255,255,255,166);
            border: 1px solid rgba(220,130,160,64);
            color: #c06080;
            min-width: 24px; min-height: 24px;
            border-radius: 12px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: rgba(245,138,176,230);
            border: none;
            border-radius: 13px;
        }
        QPushButton:hover { background: rgba(255,255,255,235); }
        QPushButton:pressed { background: rgba(230,100,150,120); }
    """


def _media_style_matcha() -> str:
    """抹茶绿 — light mint/emerald gradient, fresh and clean."""
    return """
        QFrame#matcha {
            background: transparent;
            border: 1px solid rgba(100,190,150,71);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: #3b7a5c;
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: #1e3a2e;
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(255,255,255,184);
            border: 1px solid rgba(130,200,160,46);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton#mediaStyleButton {
            background: rgba(255,255,255,153);
            border: 1px solid rgba(120,190,150,56);
            color: #48906a;
            min-width: 24px; min-height: 24px;
            border-radius: 12px;
            font-weight: 700;
        }
        QPushButton#mediaPlayButton {
            background: rgba(92,196,146,230);
            border: none;
            border-radius: 13px;
        }
        QPushButton:hover { background: rgba(255,255,255,235); }
        QPushButton:pressed { background: rgba(60,170,110,120); }
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
        self._media_style = "aurora"
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
            if style == "neon":
                return QColor(0, 230, 255, 220), QColor(255, 40, 140, 170), QColor(180, 250, 255, 130)
            if style == "velvet":
                return QColor(220, 175, 105, 210), QColor(170, 130, 75, 175), QColor(255, 220, 170, 90)
            if style == "glass":
                return QColor(255, 255, 255, 190), QColor(240, 240, 245, 140), QColor(255, 255, 255, 100)
            if style == "prism":
                return QColor(150, 170, 225, 200), QColor(200, 140, 190, 160), QColor(220, 210, 240, 90)
            if style == "blossom":
                return QColor(245, 138, 176, 230), QColor(232, 93, 144, 210), QColor(255, 255, 255, 100)
            if style == "matcha":
                return QColor(92, 196, 146, 230), QColor(61, 168, 112, 210), QColor(255, 255, 255, 100)
            # aurora (default primary) — green/teal aurora palette
            return QColor(70, 200, 150, 179), QColor(50, 170, 130, 155), QColor(100, 220, 180, 80)

        if style == "neon":
            return QColor(0, 200, 240, 120), QColor(0, 180, 220, 100), QColor(0, 230, 255, 150)
        if style == "velvet":
            return QColor(200, 170, 120, 115), QColor(160, 130, 80, 95), QColor(200, 170, 120, 100)
        if style == "glass":
            return QColor(255, 255, 255, 130), QColor(235, 235, 245, 100), QColor(255, 255, 255, 120)
        if style == "prism":
            return QColor(195, 200, 225, 105), QColor(175, 185, 215, 85), QColor(195, 200, 225, 100)
        if style == "blossom":
            return QColor(255, 255, 255, 191), QColor(245, 235, 240, 150), QColor(220, 140, 170, 51)
        if style == "matcha":
            return QColor(255, 255, 255, 184), QColor(235, 248, 240, 150), QColor(130, 200, 160, 46)
        # aurora (default secondary) — teal aurora palette
        return QColor(100, 190, 170, 89), QColor(80, 170, 150, 70), QColor(100, 200, 170, 38)

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

        # Icon centered at iconSize() within the visual rect
        icon_sz = self.iconSize()
        icon_rect = QRect(
            rect.center().x() - icon_sz.width() // 2,
            rect.center().y() - icon_sz.height() // 2,
            icon_sz.width(),
            icon_sz.height(),
        )
        mode = QIcon.Mode.Selected if self.isDown() else QIcon.Mode.Active if self.underMouse() else QIcon.Mode.Normal
        self.icon().paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter, mode, QIcon.State.Off)

    def visible_button_rect(self) -> QRect:
        return self.rect().adjusted(1, 1, -1, -1)

    def visible_circle_rect(self) -> QRect:
        return self.visible_button_rect()


class MediaRadialItem(QFrame):
    """Media control card for the radial menu, replacing standalone overlay.

    Five visual styles: Aurora, Neon, Glass, Velvet, Prism.
    Aurora is the default.
    """

    command_requested = Signal(str)
    style_selected = Signal(str)

    VALID_STYLES = frozenset({
        "aurora",
        "neon",
        "glass",
        "velvet",
        "prism",
        "blossom",
        "matcha",
    })

    def __init__(self, style: str = "aurora", parent=None):
        super().__init__(parent)
        self._style = "aurora"
        self._snapshot = None
        self._hover = False
        self._debug_overlay = False

        self.setObjectName("aurora")
        self.setFixedSize(MEDIA_CARD_WIDTH, MEDIA_CARD_HEIGHT)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

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
            14,
        )
        self._play_btn = self._mk_btn(
            "play",
            MEDIA_CONTROL_PRIMARY_SIZE,
            MEDIA_CONTROL_PRIMARY_HEIGHT,
            16,
            command="play_pause",
        )
        self._play_btn.setObjectName("mediaPlayButton")
        self._next_btn = self._mk_btn(
            "next",
            MEDIA_CONTROL_SECONDARY_SIZE,
            MEDIA_CONTROL_SECONDARY_HEIGHT,
            14,
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

        # Center controls horizontally
        group_x = round(panel_rect.left() + (panel_rect.width() - group_w) / 2)
        # Center controls vertically in the space below the track label
        track_bottom = panel_rect.top() + MEDIA_TITLE_TOP_MARGIN + MEDIA_TRACK_TOP_OFFSET + MEDIA_TRACK_HEIGHT
        available_below = max(group_h, panel_rect.bottom() - track_bottom)
        group_y = track_bottom + round((available_below - group_h) / 2)

        self._controls_widget.setGeometry(group_x, group_y, group_w, group_h)
        self._controls_layout.activate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_children()

    # -- public API --

    def set_style(self, style: str):
        style = str(style or "").strip().lower()
        if style not in self.VALID_STYLES:
            style = "aurora"
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
            "aurora": "Aurora 极光",
            "neon": "Neon Pulse 霓虹",
            "glass": "Frosted Glass 磨砂",
            "velvet": "Velvet Night 丝绒",
            "prism": "Prism 全息幻彩",
            "blossom": "Blossom 花漾粉",
            "matcha": "Matcha 抹茶绿",
        }
        for style in ("aurora", "neon", "glass", "velvet", "prism", "blossom", "matcha"):
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
        self.setProperty("hover", "false")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            self._safe_paint(painter)
        except Exception:
            # Don't let a paint crash take down the widget
            import sys as _sys, traceback as _tb
            _tb.print_exc(file=_sys.stderr)
        finally:
            painter.end()

    def _safe_paint(self, painter: QPainter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        panel_rect = self._panel_rect()
        style = self._style

        # ── shadow ──
        shadow_rect = panel_rect.adjusted(2, 8, -2, 10)
        painter.setPen(Qt.PenStyle.NoPen)
        if style == "neon":
            painter.setBrush(QColor(0, 180, 220, 32))
        elif style == "velvet":
            painter.setBrush(QColor(140, 100, 50, 22))
        elif style == "glass":
            painter.setBrush(QColor(0, 0, 0, 46))
        else:
            painter.setBrush(QColor(15, 23, 42, 52))
        painter.drawRoundedRect(shadow_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)

        # ── background gradient (per style) ──
        bg = QLinearGradient(panel_rect.topLeft(), panel_rect.bottomRight())
        if style == "aurora":
            bg.setColorAt(0.0, QColor(26, 22, 40, 250))
            bg.setColorAt(0.35, QColor(32, 26, 46, 250))
            bg.setColorAt(0.65, QColor(36, 30, 50, 250))
            bg.setColorAt(1.0, QColor(28, 26, 43, 250))
            border = QColor(180, 160, 220, 64)
        elif style == "neon":
            bg.setColorAt(0.0, QColor(10, 18, 31, 250))
            bg.setColorAt(0.5, QColor(12, 22, 38, 250))
            bg.setColorAt(1.0, QColor(10, 17, 28, 250))
            border = QColor(0, 210, 240, 89)
        elif style == "glass":
            bg.setColorAt(0.0, QColor(255, 255, 255, 20))
            bg.setColorAt(1.0, QColor(255, 255, 255, 8))
            border = QColor(255, 255, 255, 36)
        elif style == "velvet":
            bg.setColorAt(0.0, QColor(24, 20, 30, 250))
            bg.setColorAt(0.3, QColor(26, 21, 34, 250))
            bg.setColorAt(0.6, QColor(28, 22, 36, 250))
            bg.setColorAt(1.0, QColor(23, 19, 29, 250))
            border = QColor(180, 150, 100, 56)
        elif style == "prism":
            bg.setColorAt(0.0, QColor(18, 20, 29, 250))
            bg.setColorAt(0.5, QColor(22, 24, 32, 250))
            bg.setColorAt(1.0, QColor(18, 21, 28, 250))
            border = QColor(180, 180, 200, 46)
        elif style == "blossom":
            bg.setColorAt(0.0, QColor(255, 245, 248, 250))
            bg.setColorAt(0.35, QColor(255, 232, 240, 250))
            bg.setColorAt(0.65, QColor(255, 240, 245, 250))
            bg.setColorAt(1.0, QColor(252, 228, 236, 250))
            border = QColor(230, 120, 160, 77)
        elif style == "matcha":
            bg.setColorAt(0.0, QColor(246, 253, 249, 250))
            bg.setColorAt(0.35, QColor(235, 250, 242, 250))
            bg.setColorAt(0.65, QColor(242, 252, 246, 250))
            bg.setColorAt(1.0, QColor(232, 246, 239, 250))
            border = QColor(100, 190, 150, 71)
        else:  # fallback (should not reach)
            bg.setColorAt(0.0, QColor(18, 20, 29, 250))
            bg.setColorAt(0.5, QColor(22, 24, 32, 250))
            bg.setColorAt(1.0, QColor(18, 21, 28, 250))
            border = QColor(180, 180, 200, 46)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(panel_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)

        # ── layered decorations (per style) ──
        clip = QPainterPath()
        clip.addRoundedRect(panel_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)
        painter.save()
        painter.setClipPath(clip)

        if style == "aurora":
            # Vertical flowing bands — aurora borealis effect
            painter.setPen(Qt.PenStyle.NoPen)
            band_height = panel_rect.height()
            # Bottom green band
            green_band = QLinearGradient(panel_rect.topLeft(), panel_rect.bottomLeft())
            green_band.setColorAt(0.0, QColor(80, 220, 160, 0))
            green_band.setColorAt(0.65, QColor(80, 220, 160, 22))
            green_band.setColorAt(0.82, QColor(80, 200, 140, 40))
            green_band.setColorAt(1.0, QColor(60, 180, 120, 18))
            painter.setBrush(QBrush(green_band))
            painter.drawRect(panel_rect)
            # Mid teal band (slightly tilted)
            teal_band = QLinearGradient(panel_rect.topLeft() + QPointF(0, band_height * 0.30),
                                        panel_rect.bottomLeft() - QPointF(0, band_height * 0.25))
            teal_band.setColorAt(0.0, QColor(60, 210, 180, 0))
            teal_band.setColorAt(0.34, QColor(60, 210, 180, 24))
            teal_band.setColorAt(0.5, QColor(100, 230, 200, 36))
            teal_band.setColorAt(0.66, QColor(60, 200, 170, 18))
            teal_band.setColorAt(1.0, QColor(60, 200, 170, 0))
            painter.setBrush(QBrush(teal_band))
            painter.drawRect(panel_rect)
            # Upper purple-pink band
            purple_band = QLinearGradient(panel_rect.topLeft() + QPointF(0, band_height * 0.42),
                                          panel_rect.bottomLeft() - QPointF(0, band_height * 0.38))
            purple_band.setColorAt(0.0, QColor(160, 100, 220, 0))
            purple_band.setColorAt(0.38, QColor(160, 100, 220, 18))
            purple_band.setColorAt(0.5, QColor(200, 130, 240, 32))
            purple_band.setColorAt(0.62, QColor(140, 90, 200, 14))
            purple_band.setColorAt(1.0, QColor(140, 90, 200, 0))
            painter.setBrush(QBrush(purple_band))
            painter.drawRect(panel_rect)
            # Faint upper green accent
            accent_band = QLinearGradient(panel_rect.topLeft() + QPointF(0, band_height * 0.55),
                                           panel_rect.bottomLeft() - QPointF(0, band_height * 0.28))
            accent_band.setColorAt(0.0, QColor(80, 200, 140, 0))
            accent_band.setColorAt(0.45, QColor(80, 200, 140, 12))
            accent_band.setColorAt(0.55, QColor(120, 220, 170, 18))
            accent_band.setColorAt(0.65, QColor(80, 200, 140, 0))
            painter.setBrush(QBrush(accent_band))
            painter.drawRect(panel_rect)
            # Vertical streak mask overlay
            streak = QLinearGradient(panel_rect.topLeft(), panel_rect.topRight())
            streak.setColorAt(0.0, QColor(255, 255, 255, 0))
            streak.setColorAt(0.08, QColor(255, 255, 255, 22))
            streak.setColorAt(0.15, QColor(255, 255, 255, 35))
            streak.setColorAt(0.22, QColor(255, 255, 255, 0))
            streak.setColorAt(0.38, QColor(255, 255, 255, 0))
            streak.setColorAt(0.44, QColor(255, 255, 255, 28))
            streak.setColorAt(0.50, QColor(255, 255, 255, 40))
            streak.setColorAt(0.56, QColor(255, 255, 255, 0))
            streak.setColorAt(0.68, QColor(255, 255, 255, 0))
            streak.setColorAt(0.74, QColor(255, 255, 255, 25))
            streak.setColorAt(0.80, QColor(255, 255, 255, 32))
            streak.setColorAt(0.86, QColor(255, 255, 255, 0))
            streak.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(streak))
            painter.drawRect(panel_rect)
            # Outer glow
            outer_glow = QRadialGradient(panel_rect.right() - 20, panel_rect.top() + 30, 130)
            outer_glow.setColorAt(0.0, QColor(60, 180, 140, 16))
            outer_glow.setColorAt(1.0, QColor(60, 180, 140, 0))
            painter.setBrush(QBrush(outer_glow))
            painter.drawRect(panel_rect)

        elif style == "neon":
            # Grid lines
            grid_size = 16
            painter.setPen(QPen(QColor(0, 230, 255, 28), 1))
            x = panel_rect.left()
            while x < panel_rect.right():
                painter.drawLine(int(x), panel_rect.top(), int(x), panel_rect.bottom())
                x += grid_size
            painter.setPen(QPen(QColor(0, 230, 255, 18), 1))
            y = panel_rect.top()
            while y < panel_rect.bottom():
                painter.drawLine(panel_rect.left(), int(y), panel_rect.right(), int(y))
                y += grid_size
            # Scan line
            scan_y = panel_rect.top() + panel_rect.height() * 0.48
            scan = QLinearGradient(panel_rect.left(), scan_y, panel_rect.right(), scan_y + 6)
            scan.setColorAt(0.0, QColor(0, 220, 255, 0))
            scan.setColorAt(0.15, QColor(0, 220, 255, 128))
            scan.setColorAt(0.5, QColor(255, 50, 150, 102))
            scan.setColorAt(0.85, QColor(0, 220, 255, 128))
            scan.setColorAt(1.0, QColor(0, 220, 255, 0))
            painter.setPen(QPen(QBrush(scan), 1.5))
            painter.drawLine(panel_rect.left() - 30, int(scan_y + 12), panel_rect.right() + 30, int(scan_y - 10))
            # Neon glow
            glow = QRadialGradient(panel_rect.right(), panel_rect.top() + 40, 80)
            glow.setColorAt(0.0, QColor(0, 200, 230, 14))
            glow.setColorAt(1.0, QColor(0, 200, 230, 0))
            painter.setBrush(QBrush(glow))
            painter.drawRect(panel_rect)

        elif style == "glass":
            # Inner border highlight
            inner = panel_rect.adjusted(5, 5, -5, -5)
            painter.setPen(QPen(QColor(255, 255, 255, 16), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(inner, MEDIA_CARD_RADIUS - 4, MEDIA_CARD_RADIUS - 4)
            # Top-left highlight
            highlight = QLinearGradient(panel_rect.topLeft(), panel_rect.center())
            highlight.setColorAt(0.0, QColor(255, 255, 255, 22))
            highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(highlight))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(panel_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)

        elif style == "velvet":
            # Inner gold border
            inner = panel_rect.adjusted(7, 7, -7, -7)
            painter.setPen(QPen(QColor(190, 155, 105, 26), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(inner, MEDIA_CARD_RADIUS - 4, MEDIA_CARD_RADIUS - 4)
            # Warm glow orb
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(180, 140, 90, 16))
            painter.drawEllipse(panel_rect.right() - 42, panel_rect.top() + 4, 36, 36)
            painter.setBrush(QColor(160, 100, 60, 12))
            painter.drawEllipse(panel_rect.left() + 14, panel_rect.bottom() - 52, 50, 50)

        elif style == "prism":
            # Diagonal iridescent sheen
            sheen = QLinearGradient(panel_rect.topLeft() - QPointF(20, 20), panel_rect.bottomRight() + QPointF(20, 20))
            sheen.setColorAt(0.0, QColor(120, 140, 255, 0))
            sheen.setColorAt(0.25, QColor(140, 220, 255, 16))
            sheen.setColorAt(0.5, QColor(255, 160, 200, 10))
            sheen.setColorAt(0.75, QColor(160, 200, 255, 14))
            sheen.setColorAt(1.0, QColor(120, 140, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(sheen))
            painter.drawRect(panel_rect)
            # Top-right prism highlight
            prism_glow = QRadialGradient(panel_rect.right() - 30, panel_rect.top() + 20, 60)
            prism_glow.setColorAt(0.0, QColor(140, 200, 255, 14))
            prism_glow.setColorAt(1.0, QColor(140, 200, 255, 0))
            painter.setBrush(QBrush(prism_glow))
            painter.drawRect(panel_rect)

        elif style == "blossom":
            # Warm pink glow orbs
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 200, 220, 55))
            painter.drawEllipse(panel_rect.right() - 36, panel_rect.top() - 4, 38, 38)
            painter.setBrush(QColor(255, 180, 200, 35))
            painter.drawEllipse(panel_rect.left() + 10, panel_rect.bottom() - 48, 48, 48)
            # Soft warm glow
            glow = QRadialGradient(panel_rect.center().x(), panel_rect.top() + 30, 110)
            glow.setColorAt(0.0, QColor(255, 255, 255, 25))
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(glow))
            painter.drawRect(panel_rect)
            # Top highlight
            top_hl = QLinearGradient(panel_rect.topLeft(), panel_rect.center())
            top_hl.setColorAt(0.0, QColor(255, 255, 255, 30))
            top_hl.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(top_hl))
            painter.drawRoundedRect(panel_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)

        elif style == "matcha":
            # Mint green glow orbs
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(160, 230, 200, 40))
            painter.drawEllipse(panel_rect.right() - 34, panel_rect.top() - 2, 34, 34)
            painter.setBrush(QColor(140, 210, 180, 30))
            painter.drawEllipse(panel_rect.left() + 14, panel_rect.bottom() - 42, 42, 42)
            # Fresh glow
            glow = QRadialGradient(panel_rect.center().x(), panel_rect.top() + 20, 100)
            glow.setColorAt(0.0, QColor(255, 255, 255, 20))
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(glow))
            painter.drawRect(panel_rect)
            # Top highlight
            top_hl = QLinearGradient(panel_rect.topLeft(), panel_rect.center())
            top_hl.setColorAt(0.0, QColor(255, 255, 255, 28))
            top_hl.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(top_hl))
            painter.drawRoundedRect(panel_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)

        painter.restore()

        # ── top edge highlight (all styles) ──
        highlight_rect = panel_rect.adjusted(10, 7, -10, -panel_rect.height() + 16)
        painter.setPen(Qt.PenStyle.NoPen)
        hl_alpha = 22 if style == "aurora" else 22 if style == "neon" else 30 if style == "glass" else 18 if style == "velvet" else 20 if style == "prism" else 36 if style == "blossom" else 32
        painter.setBrush(QColor(255, 255, 255, hl_alpha))
        painter.drawRoundedRect(highlight_rect, 5, 5)

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
    "aurora": _media_style_aurora,
    "neon": _media_style_neon,
    "glass": _media_style_glass,
    "velvet": _media_style_velvet,
    "prism": _media_style_prism,
    "blossom": _media_style_blossom,
    "matcha": _media_style_matcha,
}


def _build_media_style_sheet(style: str) -> str:
    func = _STYLE_FUNCTIONS.get(style)
    if func is None:
        return _media_style_aurora()
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
            base_w + media_size.width() + 32,
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

    def add_media_item(self, style: str = "aurora") -> MediaRadialItem:
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
