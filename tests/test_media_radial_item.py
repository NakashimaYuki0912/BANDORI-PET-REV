"""Tests for MediaRadialItem widget and RadialMenu media integration."""
import unittest

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from radial_menu import MediaRadialItem, RadialMenu, _media_icon


_STYLES = ("cute", "cyber", "minimal", "luxury", "ghost_acrylic", "stealth_acrylic")


def _app():
    return QApplication.instance() or QApplication([])


class MediaRadialItemStyleTest(unittest.TestCase):
    """Verify each style produces visually distinct rendering."""

    @classmethod
    def setUpClass(cls):
        cls._app = _app()

    def test_all_styles_create_widget_without_crash(self):
        for style in _STYLES:
            with self.subTest(style=style):
                w = MediaRadialItem(style=style)
                self.assertIsNotNone(w)
                w.deleteLater()

    def test_cute_style_sets_pink_themed_palette(self):
        w = MediaRadialItem(style="cute")
        ss = w.styleSheet().lower()
        # cute uses pinkish hex colors
        self.assertTrue(any(c in ss for c in ("#ffc0d8", "#ffd9e9", "#ff8cc8")),
                        f"cute style missing pink hex colors: {ss[:120]}")
        w.deleteLater()

    def test_cyber_style_sets_dark_neon_palette(self):
        w = MediaRadialItem(style="cyber")
        ss = w.styleSheet().lower()
        # cyber uses neon teal/cyan hex (#00ffff, #00ffcc)
        self.assertTrue(any(c in ss for c in ("#65f2e7", "#7efff2", "#57a5ff")),
                        f"cyber style missing neon hex colors: {ss[:120]}")
        w.deleteLater()

    def test_minimal_style_is_monochrome_no_gradient(self):
        w = MediaRadialItem(style="minimal")
        ss = w.styleSheet()
        # Minimal avoids qlineargradient/qradialgradient
        self.assertNotIn("qlineargradient", ss.lower())
        self.assertNotIn("qradialgradient", ss.lower())
        w.deleteLater()

    def test_luxury_style_has_gold_tone(self):
        w = MediaRadialItem(style="luxury")
        ss = w.styleSheet().lower()
        # luxury uses gold-ish hex (#c8a84e, #d4c088)
        self.assertTrue(any(c in ss for c in ("#d7bd74", "#f4d57e", "#c99945")),
                        f"luxury style missing gold hex colors: {ss[:120]}")
        w.deleteLater()

    def test_ghost_acrylic_default_state_is_still_clearly_visible(self):
        w = MediaRadialItem(style="ghost_acrylic")
        self.assertIn("ghost_acrylic", w.objectName())
        effect = w.graphicsEffect()
        if effect is not None:
            self.assertGreaterEqual(effect.opacity(), 0.72)
        w.deleteLater()

    def test_ghost_acrylic_hover_increases_visibility(self):
        w = MediaRadialItem(style="ghost_acrylic")
        w._hover = False
        w._sync_hover_style()
        default_opacity = w.graphicsEffect().opacity() if w.graphicsEffect() else 1.0

        w._hover = True
        w._sync_hover_style()
        hover_opacity = w.graphicsEffect().opacity() if w.graphicsEffect() else 1.0

        self.assertGreater(hover_opacity, default_opacity,
                           "ghost_acrylic should become more visible on hover")
        w.deleteLater()

    def test_stealth_acrylic_stays_quiet_until_hover(self):
        w = MediaRadialItem(style="stealth_acrylic")
        w._hover = False
        w._sync_hover_style()
        default_opacity = w.graphicsEffect().opacity() if w.graphicsEffect() else 1.0

        w._hover = True
        w._sync_hover_style()
        hover_opacity = w.graphicsEffect().opacity() if w.graphicsEffect() else 1.0

        self.assertLess(default_opacity, 0.7)
        self.assertGreaterEqual(hover_opacity, 0.98)
        w.deleteLater()

    def test_invalid_style_falls_back_to_ghost_acrylic(self):
        w = MediaRadialItem(style="nonexistent_style")
        self.assertIn("ghost_acrylic", w.objectName())
        w.deleteLater()

    def test_widget_dimensions_fit_media_card(self):
        w = MediaRadialItem(style="minimal")
        # Wider than tall (media card shape)
        self.assertGreater(w.width(), w.height())
        # Match the mockup's actual .media-card, not the larger style preview cards.
        self.assertEqual(w.width(), 212)
        self.assertEqual(w.height(), 128)
        w.deleteLater()

    def test_control_buttons_are_centered_like_style_mockup(self):
        w = MediaRadialItem(style="cyber")
        w.show()
        self._app.processEvents()

        group_center = w._controls_widget.x() + w._controls_widget.width() / 2
        self.assertAlmostEqual(group_center, w.width() / 2, delta=1.0)
        panel_rect = w._panel_rect()
        bottom_gap = panel_rect.bottom() + 1 - w._controls_widget.geometry().bottom() - 1
        self.assertEqual(bottom_gap, 14)
        w.hide()
        w.deleteLater()

    def test_controls_are_structurally_independent_from_meta_and_menu(self):
        w = MediaRadialItem(style="luxury")
        self.assertIs(w._style_menu_button.parent(), w)
        self.assertIs(w._app_label.parent(), w)
        self.assertIs(w._track_label.parent(), w)
        self.assertIs(w._prev_btn.parent(), w._controls_widget)
        self.assertIs(w._play_btn.parent(), w._controls_widget)
        self.assertIs(w._next_btn.parent(), w._controls_widget)
        w.deleteLater()

    def test_controls_widget_content_is_centered_inside_card(self):
        w = MediaRadialItem(style="cyber")
        w.show()
        self._app.processEvents()

        controls = w._controls_widget
        card_center = w._panel_rect().left() + w._panel_rect().width() / 2
        controls_center = controls.geometry().center().x() + 0.5
        self.assertAlmostEqual(controls_center, card_center, delta=1.0)

        button_left = w._prev_btn.x()
        button_right = w._next_btn.x() + w._next_btn.width()
        button_center = (button_left + button_right) / 2
        self.assertAlmostEqual(button_center, controls.width() / 2, delta=1.0)
        w.hide()
        w.deleteLater()

    def test_control_buttons_are_compact(self):
        w = MediaRadialItem(style="cyber")
        self.assertEqual((w._prev_btn.width(), w._prev_btn.height()), (36, 30))
        self.assertEqual((w._next_btn.width(), w._next_btn.height()), (36, 30))
        self.assertEqual((w._play_btn.width(), w._play_btn.height()), (44, 30))
        w.deleteLater()

    def test_controls_layout_has_no_hidden_margins(self):
        w = MediaRadialItem(style="cyber")
        margins = w._controls_layout.contentsMargins()
        self.assertEqual((margins.left(), margins.top(), margins.right(), margins.bottom()), (0, 0, 0, 0))
        self.assertEqual(w._controls_layout.spacing(), 10)
        self.assertEqual(w._controls_widget.width(), 136)
        self.assertEqual(w._controls_widget.height(), 30)
        w.deleteLater()

    def test_rendered_button_cluster_center_matches_rendered_panel(self):
        for style in ("cute", "cyber", "minimal", "luxury", "stealth_acrylic"):
            with self.subTest(style=style):
                w = MediaRadialItem(style=style)
                if style == "stealth_acrylic":
                    w._hover = True
                    w._sync_hover_style()
                w.show()
                self._app.processEvents()

                image = w.grab().toImage()
                panel_rect = w._panel_rect()
                panel_center = panel_rect.left() + panel_rect.width() / 2

                circle_rects = []
                for button in (w._prev_btn, w._play_btn, w._next_btn):
                    button_rect = button.visible_circle_rect().translated(
                        w._controls_widget.x() + button.x(),
                        w._controls_widget.y() + button.y(),
                    )
                    xs = []
                    for y in range(button_rect.top(), button_rect.bottom() + 1):
                        for x in range(button_rect.left(), button_rect.right() + 1):
                            color = image.pixelColor(x, y)
                            # Count rendered button pixels, not the transparent
                            # widget box. The circles are always brighter than
                            # their card panel in every style.
                            if color.alpha() > 120 and max(color.red(), color.green(), color.blue()) > 135:
                                xs.append(x)
                    self.assertTrue(xs, f"{style} has no visible button pixels")
                    circle_rects.append((min(xs), max(xs)))

                cluster_left = min(left for left, _right in circle_rects)
                cluster_right = max(right for _left, right in circle_rects)
                cluster_center = (cluster_left + cluster_right) / 2
                self.assertAlmostEqual(cluster_center, panel_center, delta=1.0)
                w.hide()
                w.deleteLater()

    def test_media_icons_are_visually_centered(self):
        for name in ("previous", "next", "play", "pause"):
            with self.subTest(name=name):
                image = _media_icon(name).pixmap(32, 32).toImage()
                xs = []
                ys = []
                for y in range(image.height()):
                    for x in range(image.width()):
                        if image.pixelColor(x, y).alpha() > 10:
                            xs.append(x)
                            ys.append(y)

                bbox_center_x = (min(xs) + max(xs)) / 2
                bbox_center_y = (min(ys) + max(ys)) / 2
                self.assertAlmostEqual(bbox_center_x, 15.5, delta=0.6)
                self.assertAlmostEqual(bbox_center_y, 15.5, delta=0.6)

    def test_style_switcher_button_exists_in_top_right(self):
        w = MediaRadialItem(style="ghost_acrylic")
        self.assertIsNotNone(w._style_menu_button)
        self.assertEqual(w._style_menu_button.text(), "...")
        w.deleteLater()

    def test_ghost_acrylic_grabbed_panel_is_visible_on_white_background(self):
        w = MediaRadialItem(style="ghost_acrylic")
        w.move(-10000, -10000)
        w.show()
        self._app.processEvents()
        image = w.grab().toImage()
        w.hide()

        center = image.pixelColor(w.width() // 2, w.height() // 2)
        self.assertLess(center.red(), 185)
        self.assertLess(center.green(), 185)
        self.assertLess(center.blue(), 205)

    def test_acrylic_panel_paint_reaches_bottom_edge(self):
        w = MediaRadialItem(style="ghost_acrylic")
        w.move(-10000, -10000)
        w.show()
        self._app.processEvents()
        image = w.grab().toImage()
        w.hide()

        near_bottom = image.pixelColor(w.width() // 2, w.height() - 8)
        self.assertGreater(near_bottom.alpha(), 180)
        w.deleteLater()


class MediaRadialItemEmptyStateTest(unittest.TestCase):
    """No-snapshot / no-media state."""

    @classmethod
    def setUpClass(cls):
        cls._app = _app()

    def test_set_no_snapshot_shows_placeholder(self):
        w = MediaRadialItem(style="ghost_acrylic")
        w.set_snapshot(None)
        # Must not crash; app label shows placeholder
        self.assertTrue(len(w._app_label.text()) > 0)
        w.deleteLater()

    def test_set_no_snapshot_keeps_two_line_card_structure(self):
        w = MediaRadialItem(style="cyber")
        w.set_snapshot(None)
        self.assertEqual(w._app_label.text(), "No media")
        self.assertTrue(
            w._track_label.text(),
            "empty media state should keep a subtitle so the card matches style previews",
        )
        w.deleteLater()

    def test_set_no_snapshot_buttons_still_exist(self):
        """Even without media, the three buttons should exist (though may be disabled)."""
        w = MediaRadialItem(style="ghost_acrylic")
        w.set_snapshot(None)
        self.assertIsNotNone(w._prev_btn)
        self.assertIsNotNone(w._play_btn)
        self.assertIsNotNone(w._next_btn)
        w.deleteLater()


class MediaRadialItemCommandTest(unittest.TestCase):
    """Buttons emit correct commands."""

    @classmethod
    def setUpClass(cls):
        cls._app = _app()

    def test_prev_button_emits_previous_command(self):
        w = MediaRadialItem(style="cyber")
        commands = []

        def collect(cmd):
            commands.append(cmd)

        w.command_requested.connect(collect)
        w._prev_btn.clicked.emit()
        self.assertIn("previous", commands)
        w.deleteLater()

    def test_buttons_use_real_icons_not_text_glyphs(self):
        w = MediaRadialItem(style="ghost_acrylic")
        self.assertTrue(w._prev_btn.text().strip() == "")
        self.assertTrue(w._play_btn.text().strip() == "")
        self.assertTrue(w._next_btn.text().strip() == "")
        self.assertFalse(w._prev_btn.icon().isNull())
        self.assertFalse(w._play_btn.icon().isNull())
        self.assertFalse(w._next_btn.icon().isNull())
        w.deleteLater()

    def test_play_button_emits_play_pause_command(self):
        w = MediaRadialItem(style="cute")
        commands = []

        def collect(cmd):
            commands.append(cmd)

        w.command_requested.connect(collect)
        w._play_btn.clicked.emit()
        self.assertIn("play_pause", commands)
        w.deleteLater()

    def test_next_button_emits_next_command(self):
        w = MediaRadialItem(style="minimal")
        commands = []

        def collect(cmd):
            commands.append(cmd)

        w.command_requested.connect(collect)
        w._next_btn.clicked.emit()
        self.assertIn("next", commands)
        w.deleteLater()


class MediaRadialItemStyleSwitchingTest(unittest.TestCase):
    """Runtime style switching via set_style()."""

    @classmethod
    def setUpClass(cls):
        cls._app = _app()

    def test_set_style_rebuilds_stylesheet(self):
        w = MediaRadialItem(style="cute")
        cute_ss = w.styleSheet()
        w.set_style("cyber")
        cyber_ss = w.styleSheet()
        self.assertNotEqual(cute_ss, cyber_ss,
                            "set_style must rebuild the stylesheet")
        w.deleteLater()

    def test_set_style_preserves_snapshot(self):
        from media_session_manager import MediaSessionSnapshot

        w = MediaRadialItem(style="minimal")
        snap = MediaSessionSnapshot("Spotify", "Test", "Artist", "", "playing")
        w.set_snapshot(snap)
        w.set_style("luxury")
        self.assertIn("Spotify", w._app_label.text())
        w.deleteLater()

    def test_select_style_updates_style_and_emits_signal(self):
        w = MediaRadialItem(style="cute")
        seen = []
        w.style_selected.connect(lambda style: seen.append(style))

        w._select_style("cyber")

        self.assertEqual(w.style_name, "cyber")
        self.assertIn("cyber", seen)
        w.deleteLater()


class RadialMenuMediaLayoutTest(unittest.TestCase):
    """Media card positioning inside the radial menu."""

    @classmethod
    def setUpClass(cls):
        cls._app = _app()

    def test_media_item_animation_ends_inside_menu_bounds(self):
        menu = RadialMenu()
        media = menu.add_media_item(style="ghost_acrylic")
        menu.add_item("", "Chat", QColor("#9b4dff"), lambda: None, glyph="C")
        menu.add_item("", "Dress", QColor("#ef4d9b"), lambda: None, glyph="D")
        menu.add_item("", "Weather", QColor("#27a7e7"), lambda: None, glyph="W")

        screen = self._app.primaryScreen()
        self.assertIsNotNone(screen)
        center = screen.availableGeometry().center()
        menu.show_at(center)
        self._app.processEvents()

        start = QPoint(menu.width() // 2 - media.width() // 2,
                       menu.height() // 2 - media.height() // 2)
        target = start + menu._items[0].end_offset
        self.assertGreaterEqual(target.x(), 0)
        self.assertGreaterEqual(target.y(), 0)
        self.assertLessEqual(target.x() + media.width(), menu.width())
        self.assertLessEqual(target.y() + media.height(), menu.height())
        menu.dismiss()
        menu.deleteLater()

    def test_crescent_layout_places_media_right_and_actions_left(self):
        menu = RadialMenu()
        media = menu.add_media_item(style="cyber")
        menu.add_item("", "Chat", QColor("#9b4dff"), lambda: None, glyph="C")
        menu.add_item("", "Dress", QColor("#ef4d9b"), lambda: None, glyph="D")
        menu.add_item("", "Weather", QColor("#27a7e7"), lambda: None, glyph="W")

        screen = self._app.primaryScreen()
        self.assertIsNotNone(screen)
        menu.show_at(screen.availableGeometry().center())
        self._app.processEvents()

        center_x = menu.width() // 2
        media_start = QPoint(center_x - media.width() // 2,
                             menu.height() // 2 - media.height() // 2)
        media_target = media_start + menu._items[0].end_offset
        self.assertGreater(media_target.x(), center_x)

        for item in menu._items[1:]:
            target = item.widget.pos() + item.end_offset
            target_center_x = target.x() + item.widget.width() // 2
            self.assertLess(target_center_x, center_x)

        menu.dismiss()
        menu.deleteLater()

    def test_crescent_layout_keeps_action_buttons_out_of_pet_core(self):
        menu = RadialMenu()
        menu.add_media_item(style="ghost_acrylic")
        for label in ("Chat", "Dress", "Weather", "Like"):
            menu.add_item("", label, QColor("#9b4dff"), lambda: None, glyph=label[0])

        screen = self._app.primaryScreen()
        self.assertIsNotNone(screen)
        menu.show_at(screen.availableGeometry().center())
        self._app.processEvents()

        pet_core_left = menu.width() // 2 - 48
        pet_core_right = menu.width() // 2 + 48
        for item in menu._items[1:]:
            target = item.widget.pos() + item.end_offset
            target_center_x = target.x() + item.widget.width() // 2
            self.assertFalse(
                pet_core_left < target_center_x < pet_core_right,
                f"{target} overlaps the pet core area",
            )

        menu.dismiss()
        menu.deleteLater()

    def test_show_at_clamps_menu_to_visible_screen(self):
        menu = RadialMenu()
        menu.add_media_item(style="ghost_acrylic")
        menu.add_item("", "Chat", QColor("#9b4dff"), lambda: None, glyph="C")
        menu.add_item("", "Dress", QColor("#ef4d9b"), lambda: None, glyph="D")
        menu.add_item("", "Weather", QColor("#27a7e7"), lambda: None, glyph="W")

        screen = self._app.primaryScreen()
        self.assertIsNotNone(screen)
        available = screen.availableGeometry()
        menu.show_at(QPoint(available.left() + 2, available.bottom() - 2))
        self._app.processEvents()

        geometry = menu.geometry()
        self.assertGreaterEqual(geometry.left(), available.left())
        self.assertGreaterEqual(geometry.top(), available.top())
        self.assertLessEqual(geometry.right(), available.right())
        self.assertLessEqual(geometry.bottom(), available.bottom())
        menu.dismiss()
        menu.deleteLater()

    def test_show_at_preserves_anchor_after_screen_clamp(self):
        menu = RadialMenu()
        menu.add_media_item(style="ghost_acrylic")
        menu.add_item("", "Chat", QColor("#9b4dff"), lambda: None, glyph="C")
        menu.add_item("", "Dress", QColor("#ef4d9b"), lambda: None, glyph="D")
        menu.add_item("", "Weather", QColor("#27a7e7"), lambda: None, glyph="W")

        screen = self._app.primaryScreen()
        self.assertIsNotNone(screen)
        available = screen.availableGeometry()
        anchor = QPoint(available.left() + 18, available.bottom() - 18)
        menu.show_at(anchor)
        self._app.processEvents()

        expected_local = anchor - menu.geometry().topLeft()
        self.assertEqual(menu._anchor_local, expected_local)
        menu.dismiss()
        menu.deleteLater()


if __name__ == "__main__":
    unittest.main()
