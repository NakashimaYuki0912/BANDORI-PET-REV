import unittest

from media_session_manager import (
    MediaSessionSnapshot,
    choose_display_session,
    display_app_name,
    format_track_line,
)


class MediaSessionManagerTest(unittest.TestCase):
    def test_display_app_name_uses_known_short_names(self):
        self.assertEqual(display_app_name("SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"), "Spotify")
        self.assertEqual(display_app_name("Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic"), "Media Player")

    def test_format_track_line_prefers_artist_and_title(self):
        snapshot = MediaSessionSnapshot(
            app_id="Spotify",
            title="Song",
            artist="Artist",
            album="Album",
            playback_status="playing",
        )

        self.assertEqual(format_track_line(snapshot), "Artist - Song")

    def test_format_track_line_falls_back_to_title(self):
        snapshot = MediaSessionSnapshot(
            app_id="CloudMusic",
            title="Song",
            artist="",
            album="",
            playback_status="paused",
        )

        self.assertEqual(format_track_line(snapshot), "Song")

    def test_choose_display_session_prefers_playing(self):
        paused = MediaSessionSnapshot("Spotify", "Paused", "", "", "paused")
        playing = MediaSessionSnapshot("CloudMusic", "Playing", "", "", "playing")

        self.assertIs(choose_display_session([paused, playing]), playing)

    def test_choose_display_session_uses_first_when_none_playing(self):
        first = MediaSessionSnapshot("Spotify", "A", "", "", "paused")
        second = MediaSessionSnapshot("CloudMusic", "B", "", "", "paused")

        self.assertIs(choose_display_session([first, second]), first)


if __name__ == "__main__":
    unittest.main()
