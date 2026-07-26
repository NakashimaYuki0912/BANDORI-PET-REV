from PySide6.QtWidgets import QMenu


_COMPACT_TRAY_MENU_QSS = """
QMenu {
    font-size: 10px;
    padding: 4px;
}
QMenu::item {
    min-width: 70px;
    min-height: 30px;
    padding: 0px 24px 0px 16px;
}
QMenu::item:selected {
    background: rgba(236, 146, 172, 56);
    border-radius: 5px;
}
QMenu::separator {
    height: 1px;
    margin: 4px 10px;
    background: rgba(128, 128, 128, 60);
}
QMenu::right-arrow {
    width: 8px;
    height: 8px;
}
"""


def apply_compact_tray_menu_style(menu: QMenu) -> QMenu:
    font = menu.font()
    font.setPointSize(9)
    menu.setFont(font)
    menu.setStyleSheet(_COMPACT_TRAY_MENU_QSS)
    return menu
