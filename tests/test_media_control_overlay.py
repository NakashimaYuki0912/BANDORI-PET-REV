"""Tests for MediaControlOverlay (legacy standalone) and MediaRadialItem integration."""
import unittest

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect

from pet_window import MediaControlOverlay
from radial_menu import MediaRadialItem


class MediaControlOverlayTest(unittest.TestCase):
    """Legacy standalone overlay — class is kept but not created by default."""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_overlay_uses_polished_glass_panel_style(self):
        overlay = MediaControlOverlay()

        self.assertEqual(overlay.width(), 176)
        self.assertIsInstance(overlay.graphicsEffect(), QGraphicsDropShadowEffect)
        self.assertIsNotNone(overlay.findChild(object, "mediaAccentLine"))
        self.assertIn("qlineargradient", overlay.styleSheet())
        self.assertIn("mediaControlOverlay", overlay.styleSheet())

    def test_play_button_is_visually_emphasized(self):
        overlay = MediaControlOverlay()

        self.assertEqual(overlay._play_btn.size(), QSize(40, 40))
        self.assertEqual(overlay._prev_btn.size(), QSize(30, 30))
        self.assertEqual(overlay._next_btn.size(), QSize(30, 30))
        self.assertIn("mediaPlayButton", overlay.styleSheet())

    def test_translucent_window_forces_panel_background_painting(self):
        overlay = MediaControlOverlay()

        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_StyledBackground))
        self.assertIn("rgba(12, 9, 20, 252)", overlay.styleSheet())

    def test_grabbed_panel_body_has_visible_dark_surface(self):
        overlay = MediaControlOverlay()
        overlay.move(-10000, -10000)
        overlay.resize(overlay.sizeHint())
        overlay.show()
        self._app.processEvents()
        image = overlay.grab().toImage()
        overlay.hide()

        center = image.pixelColor(88, 55)
        self.assertLess(center.red(), 120)
        self.assertLess(center.green(), 90)
        self.assertLess(center.blue(), 130)


class MediaRadialItemIntegrationTest(unittest.TestCase):
    """Verify the new radial-menu media item has the same control capabilities."""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_media_radial_item_has_three_buttons(self):
        w = MediaRadialItem(style="aurora")
        self.assertIsNotNone(w._prev_btn)
        self.assertIsNotNone(w._play_btn)
        self.assertIsNotNone(w._next_btn)

    def test_media_radial_item_is_wider_than_overlay(self):
        """MediaRadialItem is a horizontal card, wider than the old square overlay."""
        w = MediaRadialItem(style="glass")
        self.assertGreater(w.width(), 200)
        self.assertLess(w.width(), 400)
        self.assertLess(w.height(), 160)

    def test_media_radial_item_empty_state_is_safe(self):
        w = MediaRadialItem(style="aurora")
        w.set_snapshot(None)
        self.assertIn("No media", w._app_label.text())

    def test_media_radial_item_play_button_emits_play_pause(self):
        w = MediaRadialItem(style="neon")
        commands = []
        w.command_requested.connect(lambda c: commands.append(c))
        w._play_btn.clicked.emit()
        self.assertIn("play_pause", commands)


if __name__ == "__main__":
    unittest.main()
