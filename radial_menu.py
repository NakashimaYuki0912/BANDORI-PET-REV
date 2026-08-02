import math
import ctypes
import os
import sys
import time
from dataclasses import dataclass

if os.name == "nt":
    import ctypes.wintypes
from typing import Callable

from PySide6.QtCore import (
    Qt, Signal, QPoint, QSize, QPropertyAnimation, QEasingCurve, QTimer,
    QParallelAnimationGroup, QVariantAnimation, QRect, QRectF, QPointF,
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
from process_utils import app_base_dir

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

MEDIA_CARD_WIDTH = 340
MEDIA_CARD_HEIGHT = 160
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

_PICTURES_DIR = os.path.join(str(app_base_dir()), "pictures")
_MEDIA_CARD_IMAGE_SPECS = {
    "sakura": (
        "01_sakura_play.png",
        "01_sakura_pause.png",
        QRectF(48, 41, 1592, 810),
        QRectF(1097, 603, 68, 76),
    ),
    "sky": (
        "02_sky_play.png",
        "02_sky_pause.png",
        QRectF(0, 0, 1694, 929),
        QRectF(1087, 634, 73, 82),
    ),
    "matcha": (
        "03_matcha_play.png",
        "03_matcha_pause.png",
        QRectF(44, 49, 1617, 834),
        QRectF(1085, 635, 70, 79),
    ),
    "ink": (
        "04_ink_play.png",
        "04_ink_pause.png",
        QRectF(21, 23, 1673, 906),
        QRectF(1090, 630, 71, 80),
    ),
    "sunset": (
        "05_sunset_play.png",
        "05_sunset_pause.png",
        QRectF(37, 57, 1623, 804),
        QRectF(1098, 628, 70, 78),
    ),
    "snow": (
        "06_snow_play.png",
        "06_snow_pause.png",
        QRectF(56, 70, 1588, 769),
        QRectF(1182, 585, 59, 66),
    ),
}

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
            # Widget size is fixed, so cache the smooth-scaled icon instead of
            # rescaling on every animation-frame repaint.
            cached = getattr(self, "_scaled_icon_cache", None)
            if cached is not None and cached[0] == icon_size:
                scaled = cached[1]
            else:
                scaled = self._icon.scaled(
                    icon_size, icon_size, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._scaled_icon_cache = (icon_size, scaled)
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

_MEDIA_STYLE_MENU_BUTTON_QSS = """
        QPushButton#mediaStyleButton {
            background: transparent;
            border: none;
            color: transparent;
        }
        QPushButton#mediaStyleButton:hover {
            background: transparent;
            border: none;
            color: transparent;
        }
"""

def _media_style_sakura() -> str:
    """桜 — soft pink with warm tones."""
    return """
        QFrame#sakura {
            background: transparent;
            border: 1px solid rgba(220,150,170,60);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(192,96,128,191);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(74,32,48,224);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(210,130,160,64);
            border: 1px solid rgba(220,150,170,32);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton:hover {
            background: rgba(210,130,160,100);
            border-color: rgba(220,150,170,70);
        }
    """

def _media_style_sky() -> str:
    """空 — clear blue sky with cloud accents."""
    return """
        QFrame#sky {
            background: transparent;
            border: 1px solid rgba(160,200,230,60);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(90,138,181,191);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(26,48,72,224);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(140,180,220,64);
            border: 1px solid rgba(160,200,230,32);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton:hover {
            background: rgba(140,180,220,100);
            border-color: rgba(160,200,230,70);
        }
    """

def _media_style_matcha() -> str:
    """抹茶绿 — light mint/emerald gradient, fresh and clean."""
    return """
        QFrame#matcha {
            background: transparent;
            border: 1px solid rgba(100,190,150,56);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(90,154,122,191);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(24,48,37,224);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(100,180,140,64);
            border: 1px solid rgba(100,190,150,32);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton:hover {
            background: rgba(100,180,140,100);
            border-color: rgba(100,190,150,70);
        }
    """

def _media_style_ink() -> str:
    """墨 — sumi-e ink wash, warm grey with brush strokes."""
    return """
        QFrame#ink {
            background: transparent;
            border: 1px solid rgba(120,120,130,36);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(85,85,85,191);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(26,26,26,224);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(80,80,90,40);
            border: 1px solid rgba(120,120,130,28);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton:hover {
            background: rgba(80,80,90,60);
            border-color: rgba(120,120,130,50);
        }
    """

def _media_style_sunset() -> str:
    """夕 — warm orange/pink dusk with horizon."""
    return """
        QFrame#sunset {
            background: transparent;
            border: 1px solid rgba(220,160,130,60);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(192,112,80,191);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(58,32,24,224);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(220,160,130,64);
            border: 1px solid rgba(220,160,130,32);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton:hover {
            background: rgba(220,160,130,100);
            border-color: rgba(220,160,130,70);
        }
    """

def _media_style_snow() -> str:
    """雪 — crisp white with ice-blue tint and snow dots."""
    return """
        QFrame#snow {
            background: transparent;
            border: 1px solid rgba(180,195,210,44);
            border-radius: 16px;
        }
        QLabel#mediaAppLabel {
            color: rgba(122,138,154,191);
            font-size: 10px;
            font-weight: 700;
        }
        QLabel#mediaTrackLabel {
            color: rgba(21,37,48,224);
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton {
            background: rgba(160,180,200,48);
            border: 1px solid rgba(180,195,210,28);
            border-radius: 13px;
            min-width: 0px; min-height: 0px;
            margin: 0px; padding: 0px;
        }
        QPushButton:hover {
            background: rgba(160,180,200,70);
            border-color: rgba(180,195,210,50);
        }
    """


_MEDIA_ICON_CACHE: dict[str, QIcon] = {}
_MEDIA_CARD_PIXMAP_CACHE: dict[tuple[str, str], QPixmap | None] = {}
_DARK_SYSTEM_CACHE: tuple[bool, float] | None = None
_MEDIA_SCRIM_COLORS = {
    "sakura": QColor(255, 248, 251, 255),
    "sky": QColor(238, 248, 255, 255),
    "matcha": QColor(250, 252, 236, 255),
    "ink": QColor(246, 243, 238, 255),
    "sunset": QColor(255, 232, 220, 255),
    "snow": QColor(250, 253, 255, 250),
}


def _media_card_pixmap(style: str, variant: str = "play") -> QPixmap | None:
    style = str(style or "").strip().lower()
    variant = "pause" if str(variant or "").strip().lower() == "pause" else "play"
    cache_key = (style, variant)
    if cache_key in _MEDIA_CARD_PIXMAP_CACHE:
        return _MEDIA_CARD_PIXMAP_CACHE[cache_key]
    spec = _MEDIA_CARD_IMAGE_SPECS.get(style)
    if spec is None:
        _MEDIA_CARD_PIXMAP_CACHE[cache_key] = None
        return None
    play_filename, pause_filename, _source_rect, _pause_rect = spec
    filename = pause_filename if variant == "pause" else play_filename
    image_path = os.path.join(_PICTURES_DIR, filename)
    if not os.path.exists(image_path):
        _MEDIA_CARD_PIXMAP_CACHE[cache_key] = None
        return None
    pixmap = QPixmap(image_path)
    if pixmap.isNull():
        _MEDIA_CARD_PIXMAP_CACHE[cache_key] = None
        return None
    _MEDIA_CARD_PIXMAP_CACHE[cache_key] = pixmap
    return pixmap


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


def _media_icon_path(name: str) -> QPainterPath:
    name = str(name or "").strip().lower()
    if name == "previous":
        return _previous_icon_path()
    if name == "next":
        return _next_icon_path()
    if name == "pause":
        return _pause_icon_path()
    return _play_icon_path()


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

    path = _media_icon_path(name)
    painter.drawPath(_center_icon_path(path))

    painter.end()
    icon = QIcon(pixmap)
    _MEDIA_ICON_CACHE[name] = icon
    return icon


class _MediaControlButton(QPushButton):
    def __init__(self, icon_name: str, *, primary: bool = False, parent=None):
        super().__init__(parent)
        self._media_style = "sakura"
        self._icon_name = str(icon_name or "play").strip().lower()
        self._primary = primary
        self.setIcon(_media_icon(self._icon_name))
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

    def set_media_icon(self, icon_name: str):
        self._icon_name = str(icon_name or "play").strip().lower()
        self.setIcon(_media_icon(self._icon_name))
        self.update()

    def _colors(self):
        style = self._media_style
        if self._primary:
            if style == "sakura":
                return QColor(236, 146, 172, 210), QColor(218, 118, 152, 185), QColor(255, 255, 255, 96)
            if style == "neon":
                return QColor(0, 230, 255, 220), QColor(255, 40, 140, 170), QColor(180, 250, 255, 130)
            if style == "velvet":
                return QColor(220, 175, 105, 210), QColor(170, 130, 75, 175), QColor(255, 220, 170, 90)
            if style == "glass":
                return QColor(255, 255, 255, 190), QColor(240, 240, 245, 140), QColor(255, 255, 255, 100)
            if style == "prism":
                return QColor(150, 170, 225, 200), QColor(200, 140, 190, 160), QColor(220, 210, 240, 90)
            if style == "matcha":
                return QColor(92, 196, 146, 230), QColor(61, 168, 112, 210), QColor(255, 255, 255, 100)
            return QColor(236, 146, 172, 210), QColor(218, 118, 152, 185), QColor(255, 255, 255, 96)

        if style == "sakura":
            return QColor(255, 252, 253, 184), QColor(247, 229, 236, 154), QColor(228, 170, 185, 72)
        if style == "neon":
            return QColor(0, 200, 240, 120), QColor(0, 180, 220, 100), QColor(0, 230, 255, 150)
        if style == "velvet":
            return QColor(200, 170, 120, 115), QColor(160, 130, 80, 95), QColor(200, 170, 120, 100)
        if style == "glass":
            return QColor(255, 255, 255, 130), QColor(235, 235, 245, 100), QColor(255, 255, 255, 120)
        if style == "prism":
            return QColor(195, 200, 225, 105), QColor(175, 185, 215, 85), QColor(195, 200, 225, 100)
        if style == "matcha":
            return QColor(255, 255, 255, 184), QColor(235, 248, 240, 150), QColor(130, 200, 160, 46)
        return QColor(255, 252, 253, 184), QColor(247, 229, 236, 154), QColor(228, 170, 185, 72)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._media_style in _MEDIA_CARD_IMAGE_SPECS and _media_card_pixmap(self._media_style) is not None:
            painter.end()
            return

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

    Six visual styles: Sakura, Sky, Matcha, Ink, Sunset, Snow.
    Sakura is the default.
    """

    command_requested = Signal(str)
    style_selected = Signal(str)

    VALID_STYLES = frozenset({
        "sakura",
        "sky",
        "matcha",
        "ink",
        "sunset",
        "snow",
    })

    def __init__(self, style: str = "sakura", parent=None):
        super().__init__(parent)
        self._style = "sakura"
        self._snapshot = None
        self._hover = False
        self._debug_overlay = False

        self.setObjectName("sakura")
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

    def _sakura_content_rect(self, panel_rect=None) -> QRectF:
        panel_rect = panel_rect or self._panel_rect()
        content_left = panel_rect.left() + max(124, round(panel_rect.width() * 0.42))
        return QRectF(
            content_left,
            panel_rect.top() + 12,
            panel_rect.right() + 1 - content_left - 12,
            panel_rect.height() - 24,
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

    def _draw_style_menu_button_chrome(self, painter: QPainter):
        menu_rect = QRectF(self._style_menu_button.geometry())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        shadow = QColor(160, 100, 120, 20)
        painter.setBrush(QBrush(shadow))
        painter.drawRoundedRect(menu_rect.adjusted(1.0, 1.5, 1.0, 2.0), 11.5, 11.5)

        menu_fill = QLinearGradient(menu_rect.topLeft(), menu_rect.bottomLeft())
        menu_fill.setColorAt(0.0, QColor(255, 247, 250, 178))
        menu_fill.setColorAt(1.0, QColor(240, 198, 211, 132))
        painter.setBrush(QBrush(menu_fill))
        painter.drawRoundedRect(menu_rect, 11.5, 11.5)

        painter.setPen(QPen(QColor(226, 162, 182, 88), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(menu_rect.adjusted(0.5, 0.5, -0.5, -0.5), 11, 11)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(132, 92, 104, 170)))
        dot_y = menu_rect.center().y()
        for dot_x in (menu_rect.center().x() - 6, menu_rect.center().x(), menu_rect.center().x() + 6):
            painter.drawEllipse(QRectF(dot_x - 1.35, dot_y - 1.35, 2.7, 2.7))
        painter.restore()

    def _draw_image_pause_patch(self, painter: QPainter, panel_rect: QRect, style: str):
        if getattr(self._play_btn, "_icon_name", "") != "pause":
            return
        spec = _MEDIA_CARD_IMAGE_SPECS.get(style)
        pause_pixmap = _media_card_pixmap(style, "pause")
        if spec is None or pause_pixmap is None or pause_pixmap.isNull():
            return

        _play_filename, _pause_filename, source_rect, pause_rect = spec
        target_rect = self._map_image_source_rect(panel_rect, source_rect, pause_rect)
        painter.drawPixmap(target_rect, pause_pixmap, pause_rect)

    def _image_play_button_rect(self, panel_rect: QRect, style: str) -> QRectF | None:
        spec = _MEDIA_CARD_IMAGE_SPECS.get(style)
        if spec is None:
            return None
        _play_filename, _pause_filename, source_rect, pause_rect = spec
        return self._map_image_source_rect(panel_rect, source_rect, pause_rect)

    def _draw_image_text_scrim(self, painter: QPainter, panel_rect: QRect, style: str):
        content_rect = self._sakura_content_rect(panel_rect)
        controls_top = self._controls_widget.geometry().top()
        top_scrim_rect = QRectF(
            content_rect.left() - 10,
            content_rect.top() + 2,
            max(24.0, content_rect.width() - 32),
            min(44.0, max(22.0, controls_top - content_rect.top() - 8)),
        )
        lower_top = content_rect.top() + 50
        lower_scrim_rect = QRectF(
            content_rect.left() - 10,
            lower_top,
            max(24.0, content_rect.width() - 8),
            max(0.0, controls_top - lower_top - 6),
        )
        colors = _MEDIA_SCRIM_COLORS
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(colors.get(style, QColor(255, 255, 255, 205))))
        painter.drawRoundedRect(top_scrim_rect, 10, 10)
        if lower_scrim_rect.height() > 1:
            painter.drawRoundedRect(lower_scrim_rect, 8, 8)
        painter.restore()

    def _image_source_target_rect(self, panel_rect: QRect, source_rect: QRectF) -> QRectF:
        """Return a centered, aspect-preserving target rect for a card image.

        The source artwork includes circular playback controls.  Scaling it to
        the card independently on each axis turns those circles into ovals, so
        use cover scaling and let the existing rounded card clip the overflow.
        """
        scale = max(
            panel_rect.width() / source_rect.width(),
            panel_rect.height() / source_rect.height(),
        )
        target_width = source_rect.width() * scale
        target_height = source_rect.height() * scale
        return QRectF(
            panel_rect.center().x() - target_width / 2,
            panel_rect.center().y() - target_height / 2,
            target_width,
            target_height,
        )

    def _map_image_source_rect(self, panel_rect: QRect, source_rect: QRectF, image_rect: QRectF) -> QRectF:
        target_rect = self._image_source_target_rect(panel_rect, source_rect)
        scale = target_rect.width() / source_rect.width()
        return QRectF(
            target_rect.left() + (image_rect.left() - source_rect.left()) * scale,
            target_rect.top() + (image_rect.top() - source_rect.top()) * scale,
            image_rect.width() * scale,
            image_rect.height() * scale,
        )

    def _layout_children(self):
        panel_rect = self._panel_rect()
        spacing = self._controls_layout.spacing()
        group_w = self._prev_btn.width() + self._play_btn.width() + self._next_btn.width() + spacing * 2
        group_h = max(self._prev_btn.height(), self._play_btn.height(), self._next_btn.height())
        self._controls_widget.setFixedSize(group_w, group_h)

        self._style_menu_button.setFixedSize(34, 26)

        if self._style in _MEDIA_CARD_IMAGE_SPECS:
            content_rect = self._sakura_content_rect(panel_rect)
            self._style_menu_button.move(
                round(content_rect.right() - 18 - self._style_menu_button.width() / 2),
                round(content_rect.top() + 18 - self._style_menu_button.height() / 2),
            )
            text_rect = content_rect.toRect().adjusted(14, 14, -44, -54)
            self._sakura_text_rect = text_rect
            self._app_label.setGeometry(text_rect.left(), text_rect.top(), text_rect.width(), 16)
            track_y = text_rect.top() + 20
            self._track_label.setGeometry(
                text_rect.left(),
                track_y,
                text_rect.width(),
                max(22, text_rect.bottom() + 1 - track_y),
            )

            image_button_rect = self._image_play_button_rect(panel_rect, self._style)
            if image_button_rect is not None:
                play_center = image_button_rect.center()
                play_offset_x = self._prev_btn.width() + spacing + self._play_btn.width() / 2
                group_x = round(play_center.x() - play_offset_x)
                group_y = round(play_center.y() - group_h / 2)
            else:
                group_x = round(content_rect.left() + 25)
                min_group_y = self._track_label.geometry().bottom() + 6
                group_y = max(min_group_y, round(content_rect.bottom() - 9 - group_h))
            group_x = max(round(panel_rect.left()), min(group_x, round(panel_rect.right() + 1 - group_w)))
            group_y = max(round(panel_rect.top()), min(group_y, round(panel_rect.bottom() + 1 - group_h)))
        else:
            self._style_menu_button.move(
                round(panel_rect.right() + 1 - MEDIA_MENU_RIGHT_MARGIN - self._style_menu_button.width()),
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

            # Center controls horizontally
            group_x = round(panel_rect.left() + (panel_rect.width() - group_w) / 2)
            # Center controls vertically in the space below the track label
            track_bottom = panel_rect.top() + MEDIA_TITLE_TOP_MARGIN + MEDIA_TRACK_TOP_OFFSET + MEDIA_TRACK_HEIGHT
            available_below = max(group_h, panel_rect.bottom() - track_bottom)
            group_y = track_bottom + round((available_below - group_h) / 2)

        self._controls_widget.setGeometry(group_x, group_y, group_w, group_h)
        self._controls_layout.activate()
        self._refresh_snapshot_labels()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_children()

    # -- public API --

    def set_style(self, style: str):
        style = str(style or "").strip().lower()
        if style not in self.VALID_STYLES:
            style = "sakura"
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
        menu_font = menu.font()
        menu_font.setPointSize(9)
        menu.setFont(menu_font)
        menu.setStyleSheet("""
            QMenu#mediaStyleMenu {
                background: rgba(255, 250, 252, 248);
                border: 1px solid rgba(226, 162, 182, 95);
                border-radius: 8px;
                padding: 4px;
                font-size: 10px;
                color: rgba(58, 32, 42, 230);
            }
            QMenu#mediaStyleMenu::item {
                min-height: 18px;
                padding: 3px 18px 3px 18px;
                border-radius: 5px;
                background: transparent;
            }
            QMenu#mediaStyleMenu::item:selected {
                background: rgba(236, 146, 172, 54);
            }
            QMenu#mediaStyleMenu::indicator {
                width: 10px;
                height: 10px;
                left: 5px;
            }
        """)
        labels = {
            "sakura": "Sakura 桜",
            "sky": "Sky 空",
            "matcha": "Matcha 抹茶绿",
            "ink": "Ink 墨",
            "sunset": "Sunset 夕",
            "snow": "Snow 雪",
        }
        for style in ("sakura", "sky", "matcha", "ink", "sunset", "snow"):
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
        self._refresh_snapshot_labels()

    def _set_elided_label(self, label: QLabel, text: str, tooltip: str = ""):
        metrics = label.fontMetrics()
        text_width = max(24, label.width() - 4)
        label.setText(metrics.elidedText(str(text or ""), Qt.TextElideMode.ElideRight, text_width))
        label.setToolTip(tooltip)

    def _refresh_snapshot_labels(self):
        snapshot = self._snapshot
        if snapshot is None:
            self._set_elided_label(self._app_label, "No media")
            self._set_elided_label(self._track_label, "No active playback")
            self._play_btn.set_media_icon("play")
            return
        from media_session_manager import display_app_name, format_track_line

        app = display_app_name(snapshot.app_id)
        track = format_track_line(snapshot)
        self._set_elided_label(self._app_label, app, app)
        self._set_elided_label(self._track_label, track, track)
        self._play_btn.set_media_icon("pause" if snapshot.playback_status == "playing" else "play")

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
        if style == "matcha":
            painter.setBrush(QColor(0, 0, 0, 12))
        else:
            painter.setBrush(QColor(0, 0, 0, 18))
        painter.drawRoundedRect(shadow_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)

        # ── background gradient (per style) ──
        # ── background gradient + border ──
        bg = QLinearGradient(panel_rect.topLeft(), panel_rect.bottomRight())
        if style == "sakura":
            bg.setColorAt(0.0, QColor(255, 245, 248, 250))
            bg.setColorAt(0.45, QColor(255, 232, 240, 250))
            bg.setColorAt(1.0, QColor(254, 242, 246, 250))
            border = QColor(220, 150, 170, 77)
        elif style == "sky":
            bg.setColorAt(0.0, QColor(244, 249, 253, 250))
            bg.setColorAt(0.45, QColor(232, 242, 250, 250))
            bg.setColorAt(1.0, QColor(240, 247, 253, 250))
            border = QColor(160, 200, 230, 77)
        elif style == "matcha":
            bg.setColorAt(0.0, QColor(250, 254, 251, 250))
            bg.setColorAt(0.35, QColor(242, 252, 246, 250))
            bg.setColorAt(0.65, QColor(246, 253, 249, 250))
            bg.setColorAt(1.0, QColor(238, 249, 243, 250))
            border = QColor(120, 200, 160, 64)
        elif style == "ink":
            bg.setColorAt(0.0, QColor(248, 246, 243, 250))
            bg.setColorAt(0.35, QColor(240, 237, 232, 250))
            bg.setColorAt(0.70, QColor(235, 231, 225, 250))
            bg.setColorAt(1.0, QColor(242, 239, 235, 250))
            border = QColor(90, 90, 100, 52)
        elif style == "sunset":
            bg.setColorAt(0.0, QColor(255, 238, 230, 250))
            bg.setColorAt(0.30, QColor(255, 220, 205, 250))
            bg.setColorAt(0.65, QColor(255, 228, 218, 250))
            bg.setColorAt(1.0, QColor(254, 240, 235, 250))
            border = QColor(220, 160, 130, 77)
        elif style == "snow":
            bg.setColorAt(0.0, QColor(251, 252, 253, 250))
            bg.setColorAt(0.45, QColor(244, 247, 250, 250))
            bg.setColorAt(1.0, QColor(249, 251, 253, 250))
            border = QColor(180, 195, 210, 56)
        else:
            bg.setColorAt(0.0, QColor(255, 245, 248, 250))
            bg.setColorAt(1.0, QColor(252, 228, 236, 250))
            border = QColor(230, 120, 160, 77)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(panel_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)

        # ── layered decorations (clipped to card shape) ──
        deco_clip = QPainterPath()
        deco_clip.addRoundedRect(panel_rect, MEDIA_CARD_RADIUS, MEDIA_CARD_RADIUS)
        painter.save()
        painter.setClipPath(deco_clip)

        image_spec = _MEDIA_CARD_IMAGE_SPECS.get(style)
        image_pixmap = _media_card_pixmap(style) if image_spec is not None else None
        if image_spec is not None and image_pixmap is not None and not image_pixmap.isNull():
            _play_filename, _pause_filename, source_rect, _pause_rect = image_spec
            painter.drawPixmap(
                self._image_source_target_rect(panel_rect, source_rect),
                image_pixmap,
                source_rect,
            )
            self._draw_image_text_scrim(painter, panel_rect, style)
            self._draw_image_pause_patch(painter, panel_rect, style)
            painter.restore()
            if self._debug_overlay:
                self._draw_debug_overlay(painter)
            return

        if style == "sakura":
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            content_rect = self._sakura_content_rect(panel_rect)

            panel_fill = QLinearGradient(content_rect.topLeft(), content_rect.bottomRight())
            panel_fill.setColorAt(0.0, QColor(255, 253, 254, 178))
            panel_fill.setColorAt(0.55, QColor(255, 246, 249, 158))
            panel_fill.setColorAt(1.0, QColor(255, 238, 244, 148))
            painter.setPen(QPen(QColor(228, 170, 185, 118), 1.15))
            painter.setBrush(QBrush(panel_fill))
            painter.drawRoundedRect(content_rect, 18, 18)
            painter.setPen(QPen(QColor(255, 255, 255, 135), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(content_rect.adjusted(1.5, 1.5, -1.5, -1.5), 16, 16)

            menu_w = 30
            menu_h = 23
            menu_rect = QRectF(
                content_rect.right() - 35,
                content_rect.top() + 8,
                menu_w,
                menu_h,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            menu_fill = QLinearGradient(menu_rect.topLeft(), menu_rect.bottomLeft())
            menu_fill.setColorAt(0.0, QColor(255, 247, 250, 170))
            menu_fill.setColorAt(1.0, QColor(240, 198, 211, 125))
            painter.setBrush(QBrush(menu_fill))
            painter.drawRoundedRect(menu_rect, 11.5, 11.5)
            painter.setPen(QPen(QColor(226, 162, 182, 82), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(menu_rect.adjusted(0.5, 0.5, -0.5, -0.5), 11, 11)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(132, 92, 104, 165)))
            dot_y = menu_rect.center().y()
            for dot_x in (menu_rect.center().x() - 6, menu_rect.center().x(), menu_rect.center().x() + 6):
                painter.drawEllipse(QRectF(dot_x - 1.35, dot_y - 1.35, 2.7, 2.7))

            def draw_sakura_flower(cx: float, cy: float, scale: float = 1.0,
                                   fill_alpha: int = 150, outline_alpha: int = 180):
                petal_fill = QColor(246, 178, 196, fill_alpha)
                petal_line = QColor(220, 128, 156, outline_alpha)
                center_fill = QColor(232, 108, 145, min(200, fill_alpha + 20))

                painter.save()
                painter.translate(cx, cy)

                painter.setPen(QPen(petal_line, 1))
                painter.setBrush(QBrush(petal_fill))
                for ang in (0, 72, 144, 216, 288):
                    painter.save()
                    painter.rotate(ang)
                    painter.drawEllipse(QRectF(-7 * scale, -18 * scale, 14 * scale, 24 * scale))
                    painter.restore()

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(center_fill))
                painter.drawEllipse(QRectF(-3 * scale, -3 * scale, 6 * scale, 6 * scale))
                painter.restore()

            deco_left = panel_rect.left() + 18
            deco_top = panel_rect.top() + 8

            branch_pen = QPen(
                QColor(154, 104, 112, 130),
                4.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.setPen(branch_pen)
            painter.drawLine(QPointF(deco_left + 6, deco_top + 14), QPointF(deco_left + 54, deco_top + 20))
            painter.drawLine(QPointF(deco_left + 54, deco_top + 20), QPointF(deco_left + 82, deco_top + 10))
            painter.drawLine(QPointF(deco_left + 40, deco_top + 18), QPointF(deco_left + 26, deco_top + 34))

            draw_sakura_flower(deco_left + 22, deco_top + 16, 0.55, 135, 165)
            draw_sakura_flower(deco_left + 44, deco_top + 24, 0.50, 130, 160)
            draw_sakura_flower(deco_left + 66, deco_top + 12, 0.52, 132, 162)
            draw_sakura_flower(deco_left + 28, deco_top + 36, 0.46, 120, 150)

            furin_cx = deco_left + 58
            furin_top = deco_top + 12

            painter.setPen(QPen(QColor(225, 120, 150, 170), 1.8))
            painter.drawLine(QPointF(furin_cx, furin_top), QPointF(furin_cx, furin_top + 14))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(236, 146, 172, 170)))
            painter.drawEllipse(QRectF(furin_cx - 2.5, furin_top + 12, 5, 5))

            glass_x = furin_cx - 17
            glass_y = furin_top + 16
            glass_w = 34
            glass_h = 24
            painter.setPen(QPen(QColor(233, 136, 164, 185), 1.8))
            painter.setBrush(QBrush(QColor(255, 240, 245, 85)))

            bell_path = QPainterPath()
            bell_path.moveTo(glass_x + 5, glass_y + glass_h - 6)
            bell_path.quadTo(glass_x + 2, glass_y + 6, furin_cx, glass_y + 1)
            bell_path.quadTo(
                glass_x + glass_w - 2,
                glass_y + 6,
                glass_x + glass_w - 5,
                glass_y + glass_h - 6,
            )
            zx = glass_x + glass_w - 5
            zy = glass_y + glass_h - 6
            bell_path.lineTo(zx - 4, zy + 3)
            bell_path.lineTo(zx - 8, zy)
            bell_path.lineTo(zx - 12, zy + 3)
            bell_path.lineTo(zx - 16, zy)
            bell_path.lineTo(zx - 20, zy + 3)
            bell_path.lineTo(zx - 24, zy)
            bell_path.lineTo(glass_x + 5, zy)
            bell_path.closeSubpath()
            painter.drawPath(bell_path)

            painter.setPen(QPen(QColor(255, 255, 255, 145), 1.5))
            painter.drawLine(QPointF(glass_x + 8, glass_y + 7), QPointF(glass_x + 13, glass_y + 3))

            painter.setPen(QPen(QColor(228, 132, 160, 175), 1.4))
            painter.drawLine(QPointF(furin_cx, glass_y + 10), QPointF(furin_cx, glass_y + glass_h + 4))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(237, 152, 176, 175)))
            painter.drawEllipse(QRectF(furin_cx - 2.2, glass_y + glass_h + 2, 4.4, 4.4))

            draw_sakura_flower(furin_cx, glass_y + 11, 0.42, 150, 175)

            paper_top = glass_y + glass_h + 6
            painter.setPen(QPen(QColor(230, 138, 165, 165), 1.2))
            painter.drawLine(QPointF(furin_cx, glass_y + glass_h + 6), QPointF(furin_cx - 2, paper_top + 4))

            painter.save()
            painter.translate(furin_cx - 5, paper_top + 6)
            painter.rotate(6)
            painter.setPen(QPen(QColor(230, 138, 165, 150), 1.0))
            painter.setBrush(QBrush(QColor(255, 236, 242, 125)))
            painter.drawRect(QRectF(0, 0, 12, 24))
            painter.setPen(QPen(QColor(228, 164, 180, 120), 1.0))
            painter.drawLine(QPointF(2, 17), QPointF(10, 17))
            painter.drawLine(QPointF(3, 20), QPointF(9, 20))
            painter.restore()
            draw_sakura_flower(furin_cx + 1, paper_top + 18, 0.22, 135, 160)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(243, 178, 194, 130)))
            for px, py, pw, ph in (
                (deco_left + 78, deco_top + 16, 8, 12),
                (deco_left + 93, deco_top + 38, 8, 12),
                (deco_left + 80, deco_top + 64, 8, 12),
                (deco_left + 103, deco_top + 54, 8, 12),
            ):
                painter.save()
                painter.translate(px, py)
                painter.rotate(-28)
                painter.drawEllipse(QRectF(-pw / 2, -ph / 2, pw, ph))
                painter.restore()

            draw_sakura_flower(deco_left + 16, panel_rect.bottom() - 22, 0.58, 125, 160)

            painter.restore()
        elif style == "sky":
            painter.setPen(Qt.PenStyle.NoPen)
            r, t = panel_rect.right(), panel_rect.top()
            painter.setBrush(QBrush(QColor(255, 180, 60, 180)))
            painter.drawEllipse(r - 64, t - 6, 56, 56)
            painter.setBrush(QBrush(QColor(140, 180, 210, 180)))
            painter.setPen(QPen(QColor(120, 160, 195, 150), 1.0))
            painter.drawRoundedRect(QRectF(r - 90, t + 55, 85, 18), 9, 9)
        elif style == "matcha":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(140, 210, 180, 90))
            painter.drawEllipse(panel_rect.right() - 34, panel_rect.top() - 2, 34, 34)
            painter.setBrush(QColor(120, 190, 160, 70))
            painter.drawEllipse(panel_rect.left() + 14, panel_rect.bottom() - 42, 42, 42)
            painter.setBrush(QColor(100, 180, 150, 55))
            painter.drawEllipse(panel_rect.left() + 60, panel_rect.top() + 50, 28, 28)
        elif style == "ink":
            r, t, b = panel_rect.right(), panel_rect.top(), panel_rect.bottom()
            # Mountain silhouette using drawPolygon
            painter.setBrush(QBrush(QColor(45, 40, 35, 180)))
            pts1 = QPolygon([
                QPoint(r - 100, b), QPoint(r - 90, b - 22), QPoint(r - 55, b - 35),
                QPoint(r - 30, b - 28), QPoint(r - 5, b - 50),
                QPoint(r + 5, b + 5), QPoint(r - 100, b + 5),
            ])
            painter.drawPolygon(pts1)
            # Lighter mountain behind
            painter.setBrush(QBrush(QColor(55, 50, 45, 120)))
            pts2 = QPolygon([
                QPoint(r - 125, b), QPoint(r - 80, b - 30), QPoint(r - 30, b - 15),
                QPoint(r - 10, b - 10), QPoint(r + 5, b + 5), QPoint(r - 125, b + 5),
            ])
            painter.drawPolygon(pts2)
            # Ink splash dots
            painter.setBrush(QBrush(QColor(45, 40, 35, 200)))
            dots = [(70, 16, 7), (95, 30, 5), (52, 45, 6), (110, 48, 5), (78, 60, 6), (100, 12, 4)]
            for dx, dy, d in dots:
                painter.drawEllipse(r - dx - d // 2, t + dy - d // 2, d, d)
        elif style == "sunset":
            painter.setPen(Qt.PenStyle.NoPen)
            r, t, l = panel_rect.right(), panel_rect.top(), panel_rect.left()
            painter.setBrush(QBrush(QColor(255, 140, 60, 180)))
            painter.drawEllipse(r - 78, t - 8, 72, 72)
            painter.setPen(QPen(QColor(200, 130, 90, 150), 1.5))
            painter.drawLine(QPoint(l + 20, t + 54), QPoint(r - 20, t + 54))
        elif style == "snow":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(140, 165, 195, 150)))
            snowflakes = [(50, 18, 5), (72, 40, 4), (30, 55, 6), (58, 75, 5), (90, 10, 4), (80, 60, 5), (42, 82, 4), (96, 45, 5)]
            for sx, sy, sr in snowflakes:
                painter.drawRoundedRect(QRectF(panel_rect.right() - sx, panel_rect.top() + sy, sr, sr), 1, 1)

        painter.restore()
        if style != "sakura":
            self._draw_style_menu_button_chrome(painter)
        # ── top edge highlight (all styles) ──
        highlight_rect = panel_rect.adjusted(10, 7, -10, -panel_rect.height() + 16)
        painter.setPen(Qt.PenStyle.NoPen)
        hl_alpha = 32 if style == "matcha" else 22
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
    "sakura": _media_style_sakura,
    "sky": _media_style_sky,
    "matcha": _media_style_matcha,
    "ink": _media_style_ink,
    "sunset": _media_style_sunset,
    "snow": _media_style_snow,
}


def _build_media_style_sheet(style: str) -> str:
    func = _STYLE_FUNCTIONS.get(style)
    if func is None:
        return _media_style_sakura() + _MEDIA_STYLE_MENU_BUTTON_QSS
    return func() + _MEDIA_STYLE_MENU_BUTTON_QSS


@dataclass
class _ItemData:
    widget: QWidget
    start_offset: QPoint
    end_offset: QPoint
    opacity_effect: QGraphicsOpacityEffect
    is_media: bool = False


class RadialListRow(QWidget):
    """Card-style row with left color strip, line icon, title + subtitle."""
    clicked = Signal()

    @staticmethod
    def _draw_chat_icon(p, x, y, w, h, color):
        # Speech bubble: rounded rect + triangular tail
        body = QRectF(x + 1, y + 1, w - 2, h - 6)
        p.drawRoundedRect(body, 3, 3)
        tail = QPainterPath()
        bx, by = body.right() - w * 0.3, body.bottom()
        tail.moveTo(bx, by)
        tail.lineTo(bx + 5, by + 5)
        tail.lineTo(bx + 8, by)
        tail.closeSubpath()
        p.drawPath(tail)

    @staticmethod
    def _draw_costume_icon(p, x, y, w, h, color):
        # Hanger shape: horizontal bar + triangle body
        p.drawLine(int(x + w / 2), y + 1, int(x + w / 2), y + 5)
        p.drawLine(x + 2, y + 5, x + w - 2, y + 5)
        p.drawLine(x + 3, y + 5, x + 1, y + h - 1)
        p.drawLine(x + w - 3, y + 5, x + w - 1, y + h - 1)
        p.drawLine(x + 1, y + h - 1, x + w - 1, y + h - 1)

    @staticmethod
    def _draw_weather_icon(p, x, y, w, h, color):
        # Sun: center circle + 4 rays
        cx, cy = x + w / 2, y + h / 2
        p.drawEllipse(int(cx - 3), int(cy - 3), 6, 6)
        p.drawLine(int(cx), y, int(cx), y + 2)
        p.drawLine(int(cx), y + h - 2, int(cx), y + h)
        p.drawLine(x, int(cy), x + 2, int(cy))
        p.drawLine(x + w - 2, int(cy), x + w, int(cy))

    @staticmethod
    def _draw_lock_icon(p, x, y, w, h, color):
        # Padlock: rounded body + shackle arc + keyhole
        p.drawRoundedRect(QRectF(x + 2, y + 6, w - 4, h - 7), 2, 2)
        p.drawArc(QRectF(x + 4, y + 1, w - 8, h - 7), 0, 180 * 16)
        kx, ky = int(x + w / 2 - 1), int(y + h / 2 + 4)
        p.drawEllipse(kx, ky, 2, 2)

    _ICON_DRAWERS = ("chat", "costume", "weather", "lock")

    def __init__(self, label: str, color: QColor, icon_kind: str = "", subtitle: str = "",
                 enabled: bool = True, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._icon_kind = icon_kind
        self._subtitle = subtitle
        self._enabled = enabled
        self._hover = False
        self.setFixedHeight(46)
        self.setMinimumWidth(130)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_label(self, label: str):
        self._label = label
        self.update()

    def set_subtitle(self, subtitle: str):
        self._subtitle = subtitle
        self.update()

    def _is_dark_system(self) -> bool:
        # darkdetect.isDark() hits the Windows registry; paintEvent runs per
        # animation frame for every row, so cache the answer for ~1s.
        global _DARK_SYSTEM_CACHE
        now = time.monotonic()
        cached = _DARK_SYSTEM_CACHE
        if cached is not None and now - cached[1] < 1.0:
            return cached[0]
        try:
            import darkdetect
            result = bool(darkdetect.isDark())
        except Exception:
            result = True  # default to dark if detection fails
        _DARK_SYSTEM_CACHE = (result, now)
        return result

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            dark = self._is_dark_system()

            if dark:
                # Dark theme: dark card + light icons + light text
                bg = QColor(20, 20, 30, 35 if not self._hover else 50)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(bg))
                p.drawRoundedRect(QRectF(6, 2, w - 12, h - 4), 8, 8)

                strip = QColor(self._color)
                strip.setAlpha(200)
                p.setBrush(QBrush(strip))
                p.drawRoundedRect(QRectF(6, 6, 3, h - 12), 1.5, 1.5)

                icon_bg = QColor(self._color)
                icon_bg.setAlpha(50 if not self._hover else 70)
                p.setBrush(QBrush(icon_bg))
                p.setPen(Qt.PenStyle.NoPen)

                icon_stroke = QColor(255, 255, 255, 210 if not self._hover else 245)
                title_color = QColor(245, 245, 255, 225 if not self._hover else 250)
                sub_color = QColor(180, 180, 200, 170 if not self._hover else 210)
            else:
                # Light theme: white card + colored icons + dark text
                bg = QColor(255, 255, 255, 200 if not self._hover else 230)
                p.setPen(QPen(QColor(0, 0, 0, 12), 0.5))
                p.setBrush(QBrush(bg))
                p.drawRoundedRect(QRectF(6, 2, w - 12, h - 4), 8, 8)

                strip = QColor(self._color)
                strip.setAlpha(180)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(strip))
                p.drawRoundedRect(QRectF(6, 6, 3, h - 12), 1.5, 1.5)

                icon_bg = QColor(self._color)
                icon_bg.setAlpha(35 if not self._hover else 55)
                p.setBrush(QBrush(icon_bg))
                p.setPen(Qt.PenStyle.NoPen)

                icon_stroke = QColor(self._color)
                icon_stroke.setAlpha(210 if not self._hover else 240)
                title_color = QColor(30, 30, 50, 220 if not self._hover else 245)
                sub_color = QColor(90, 90, 115, 150 if not self._hover else 190)

            # Icon area
            icon_x, icon_y = 18, (h - 28) // 2
            icon_rect = QRectF(icon_x, icon_y, 28, 28)
            p.drawRoundedRect(icon_rect, 7, 7)

            # Line icon
            if self._icon_kind in self._ICON_DRAWERS:
                pen = QPen(icon_stroke, 1.4)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                method = getattr(self, "_draw_" + self._icon_kind + "_icon", None)
                if method:
                    try:
                        method(p, icon_x + 3, icon_y + 3, 22, 22, icon_stroke)
                    except Exception:
                        pass

            # Title
            text_x = icon_x + 36
            font = p.font()
            font.setPointSize(10)
            font.setBold(True)
            p.setFont(font)
            p.setPen(title_color)
            p.drawText(QRectF(text_x, 5, w - text_x - 12, 20),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, self._label)

            # Subtitle
            if self._subtitle:
                font.setPointSize(8)
                font.setBold(False)
                p.setFont(font)
                p.setPen(sub_color)
                p.setPen(sub_color)
                p.drawText(QRectF(text_x, 24, w - text_x - 12, 16),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._subtitle)
        except Exception:
            pass

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            self.clicked.emit()


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
        self._use_stack = False
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

    def _is_row_layout(self) -> bool:
        return any(isinstance(it.widget, RadialListRow) for it in self._items)

    def _menu_popup_size(self, has_media: bool) -> QSize:
        if self._is_row_layout():
            n_rows = sum(1 for it in self._items if isinstance(it.widget, RadialListRow))
            list_h = n_rows * 54 + 8
            list_w = 190
            if has_media:
                gap = 130  # pet sits between list and card
                ms = self._media_item_size()
                w = list_w + gap + ms.width() + 24
                h = max(list_h, ms.height()) + 24
                return QSize(w, h)
            return QSize(list_w + 24, list_h + 16)
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

    def _row_top_left(self, center: QPoint, size: QSize, has_media: bool) -> QPoint:
        """Position the row-layout menu so the pet stays visible on screen.

        Mid-screen the pet sits in the wide gap (282px from the window's left
        edge). When the pet is near a screen edge, move it to the window's near
        edge instead, so the list and card extend into the free space rather
        than covering the pet after the window gets clamped.
        """
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else None
        margin = 4
        if has_media:
            pad = 12
            list_w = 190
            media_w = self._media_item_size().width()
            need = 65 + pad + list_w + pad + media_w  # one side's worth of content
            if avail is not None:
                room_left = center.x() - avail.left()
                room_right = avail.right() - center.x()
            else:
                room_left = room_right = need
            if room_right >= need and room_left < 282:
                pet_off_x = 65          # near left edge: content extends right
            elif room_left >= need and room_right < 282:
                pet_off_x = size.width() - 65  # near right edge: content extends left
            else:
                pet_off_x = 282         # normal: pet centered in the gap
        else:
            pet_off_x = size.width() // 2
        x = center.x() - pet_off_x
        y = center.y() - size.height() // 2
        if avail is not None:
            x = max(avail.left() + margin, min(x, avail.right() - size.width() + 1 - margin))
            y = max(avail.top() + margin, min(y, avail.bottom() - size.height() + 1 - margin))
        return QPoint(x, y)

    def _prefer_stack(self, center: QPoint, has_media: bool) -> bool:
        """True when the wide horizontal row cannot fit fully on screen
        (pet near an edge), so we should use the compact vertical stack."""
        if not has_media:
            return False
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        if screen is None:
            return False
        avail = screen.availableGeometry()
        row_size = self._menu_popup_size(has_media)
        row_left = center.x() - 282  # normal row: pet sits 282px from window left
        row_right = row_left + row_size.width()
        return not (avail.left() + 4 <= row_left and row_right <= avail.right() - 4)

    def _menu_stack_size(self, has_media: bool) -> QSize:
        """Compact vertical-stack window: rows on top, media card below."""
        if not has_media:
            return self._menu_popup_size(has_media)
        n_rows = sum(1 for it in self._items if isinstance(it.widget, RadialListRow))
        list_h = n_rows * 54 + 8
        ms = self._media_item_size()
        w = max(190, ms.width()) + 24
        h = list_h + ms.height() + 44
        return QSize(w, h)

    def _stack_top_left(self, center: QPoint, size: QSize, has_media: bool) -> QPoint:
        """Position the vertical stack on the pet's screen-interior side."""
        del has_media
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else None
        margin = 4
        pet_hw = 65
        if avail is not None:
            room_left = center.x() - avail.left()
            room_right = avail.right() - center.x()
        else:
            room_left = room_right = 1
        if room_right >= room_left:
            x = center.x() + pet_hw + margin
        else:
            x = center.x() - pet_hw - margin - size.width()
        y = center.y() - size.height() // 2
        if avail is not None:
            x = max(avail.left() + margin, min(x, avail.right() - size.width() + 1 - margin))
            y = max(avail.top() + margin, min(y, avail.bottom() - size.height() + 1 - margin))
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

    def add_row_item(self, label: str, color: QColor,
                     on_click: Callable, icon_kind: str = "", subtitle: str = "",
                     enabled: bool = True) -> RadialListRow:
        w = RadialListRow(label, color, icon_kind=icon_kind, subtitle=subtitle,
                          enabled=enabled, parent=self)
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
        return w

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

    def add_media_item(self, style: str = "sakura") -> MediaRadialItem:
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

        if self._is_row_layout():
            # Near a screen edge the wide row would clamp and cover the pet:
            # fall back to the compact vertical stack there. Mid-screen keeps
            # the tuned horizontal row.
            self._use_stack = self._prefer_stack(center, has_media)
            if self._use_stack:
                popup_size = self._menu_stack_size(has_media)
                top_left = self._stack_top_left(center, popup_size, has_media)
            else:
                popup_size = self._menu_popup_size(has_media)
                top_left = self._row_top_left(center, popup_size, has_media)
        else:
            popup_size = self._menu_popup_size(has_media)
            top_left = self._clamped_top_left(center, popup_size)
        total_w = popup_size.width()
        total_h = popup_size.height()

        self.setGeometry(top_left.x(), top_left.y(), total_w, total_h)

        self._anchor_local = center - top_left
        cx = self._anchor_local.x()
        cy = self._anchor_local.y()

        try:
            if self._is_row_layout():
                self._layout_vertical_list(cx, cy, has_media)
            elif has_media:
                self._layout_with_media(cx, cy)
            else:
                self._layout_circle(cx, cy, range(n))

            for item in self._items:
                item.widget.show()
        except Exception:
            self._is_showing = False
            return

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

    def _layout_vertical_list(self, cx: int, cy: int, has_media: bool):
        """List rows + media card arranged so neither block covers the pet.

        cx is the pet's position inside this window. Mid-screen this keeps the
        tuned layout (list at the left edge, card at the right edge, pet in the
        wide gap). When the window was clamped at a screen edge the pet no longer
        falls in the gap, so the blocks are rearranged on the pet's free side.
        """
        if self._use_stack:
            self._layout_vertical_stack(cx, cy, has_media)
            return

        pad = 12
        row_h = 54
        list_w = 190
        row_indices = []
        media_idx = None
        for i, item in enumerate(self._items):
            if item.is_media:
                media_idx = i
            elif isinstance(item.widget, RadialListRow):
                row_indices.append(i)

        list_top = (self.height() - len(row_indices) * row_h) // 2

        if media_idx is None:
            list_x = pad
            card_x = 0
        else:
            media = self._items[media_idx]
            mw = media.widget.width()
            mh = media.widget.height()
            list_x = pad
            card_x = self.width() - mw - pad
            if not (list_x + list_w < cx < card_x):
                # Pet is not inside the gap (window got clamped at a screen edge).
                pet_hw = 65  # visible-model half width (matches the 130px gap)
                room_left = cx - pad
                room_right = self.width() - cx - pad
                need = list_w + mw + 2 * pad
                if room_right >= need and room_left < mw + pad:
                    # pet near the left edge: card then list, both to the right
                    card_x = cx + pet_hw + pad
                    list_x = card_x + mw + pad
                    if list_x + list_w > self.width() - pad:
                        list_x = self.width() - list_w - pad
                elif room_left >= need and room_right < list_w + pad:
                    # pet near the right edge: list then card, both to the left
                    list_x = cx - pet_hw - pad - list_w
                    card_x = list_x - pad - mw
                    if card_x < pad:
                        card_x = pad
                elif room_left >= list_w + pad and room_right >= mw + pad:
                    # room on both sides: pull the blocks up against the pet
                    list_x = cx - pet_hw - pad - list_w
                    card_x = cx + pet_hw + pad
                elif room_right >= room_left:
                    # extreme corner: list closest to the pet, card beyond
                    list_x = cx + pet_hw + pad
                    card_x = list_x + list_w + pad
                    if card_x + mw > self.width() - pad:
                        card_x = max(self.width() - mw - pad, list_x + 8)
                else:
                    # extreme corner: list closest to the pet, card beyond
                    list_x = cx - pet_hw - pad - list_w
                    card_x = list_x - pad - mw
                    if card_x < pad:
                        card_x = max(pad, list_x - 8)
                    if card_x + mw > self.width() - pad:
                        card_x = self.width() - mw - pad

        for j, i in enumerate(row_indices):
            item = self._items[i]
            item.widget.setFixedWidth(list_w)
            item.widget.move(list_x, list_top + j * row_h)
            item.end_offset = QPoint(0, 0)
            item.start_offset = QPoint(0, 0)

        if media_idx is not None:
            media = self._items[media_idx]
            media.widget.move(card_x, (self.height() - media.widget.height()) // 2)
            media.end_offset = QPoint(0, 0)
            media.start_offset = QPoint(0, 0)

    def _layout_vertical_stack(self, cx: int, cy: int, has_media: bool):
        """Compact vertical stack used near screen edges: rows on top,
        media card below, aligned to the side away from the pet."""
        del cx, cy
        pad = 12
        row_h = 54
        list_w = 190
        row_indices = []
        media_idx = None
        for i, item in enumerate(self._items):
            if item.is_media:
                media_idx = i
            elif isinstance(item.widget, RadialListRow):
                row_indices.append(i)

        list_top = pad
        for j, i in enumerate(row_indices):
            item = self._items[i]
            item.widget.setFixedWidth(list_w)
            item.widget.move(pad, list_top + j * row_h)
            item.end_offset = QPoint(0, 0)
            item.start_offset = QPoint(0, 0)

        if media_idx is not None:
            media = self._items[media_idx]
            media.widget.move(pad, list_top + len(row_indices) * row_h + 12)
            media.end_offset = QPoint(0, 0)
            media.start_offset = QPoint(0, 0)

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
        if not self._is_row_layout():
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
            if self._is_row_layout():
                pass
            else:
                self._toggle_locked()
        else:
            self.dismiss()

    def paintEvent(self, event):
        if self._is_row_layout():
            return
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
