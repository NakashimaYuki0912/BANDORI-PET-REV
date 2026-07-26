import sys
import os
import importlib.util
from pathlib import Path


def prefer_local_pyside6_fluent_widgets() -> None:
    """Prefer the repo's PySide6 qfluentwidgets checkout during source runs."""
    root = Path(__file__).resolve().parent
    local_fluent = root / "third_party" / "PyQt-Fluent-Widgets"
    if not (local_fluent / "qfluentwidgets" / "__init__.py").exists():
        return

    local_path = str(local_fluent)
    try:
        sys.path.remove(local_path)
    except ValueError:
        pass
    sys.path.insert(0, local_path)


def assert_pyside6_fluent_widgets() -> None:
    assert_pyside6_frameless_window()
    try:
        from qfluentwidgets.common import style_sheet
    except Exception:
        return
    qcolor_module = getattr(style_sheet.QColor, "__module__", "")
    if not qcolor_module.startswith("PySide6."):
        raise RuntimeError(
            "qfluentwidgets is using PyQt5, but BandoriPet uses PySide6. "
            "Install the PySide6 Fluent Widgets branch and remove the PyQt5 package, "
            "or run: python3 -m pip uninstall PyQt-Fluent-Widgets PyQt5-Frameless-Window"
        )


def assert_pyside6_frameless_window() -> None:
    spec = importlib.util.find_spec("qframelesswindow")
    if spec is None or spec.origin is None:
        return
    try:
        header = Path(spec.origin).read_text(encoding="utf-8", errors="ignore")[:2048]
    except OSError:
        return
    if "PyQt5-Frameless-Window" in header or "from PyQt5" in header:
        raise RuntimeError(
            "qframelesswindow is using PyQt5, but BandoriPet uses PySide6. "
            "Run: python3 -m pip install --force-reinstall --no-deps "
            "PySideSix-Frameless-Window==0.8.1"
        )


def _candidate_font_files() -> list[Path]:
    candidates: list[Path] = []
    if sys.platform.startswith("win"):
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        fonts = windir / "Fonts"
        candidates.extend([
            fonts / "msyh.ttc",
            fonts / "msyhbd.ttc",
            fonts / "segoeui.ttf",
            fonts / "arial.ttf",
        ])
    elif sys.platform == "darwin":
        candidates.extend([
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        ])
    else:
        candidates.extend([
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ])
    return candidates


def apply_qt_font_fallback(app=None) -> bool:
    """Install and select a readable app font after QApplication is created."""
    try:
        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtWidgets import QApplication
    except Exception:
        return False

    loaded_families: list[str] = []
    for font_file in _candidate_font_files():
        if not font_file.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        if font_id >= 0:
            loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))

    preferred = [
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Segoe UI",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Noto Sans CJK",
        "DejaVu Sans",
        "Arial",
    ]
    available = set(QFontDatabase.families()) | set(loaded_families)
    family = next((name for name in preferred if name in available), "")
    if not family:
        return False

    target = app or QApplication.instance()
    if target is None:
        return False
    target.setFont(QFont(family))
    return True


prefer_local_pyside6_fluent_widgets()
assert_pyside6_frameless_window()
