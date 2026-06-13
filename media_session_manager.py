from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MediaSessionSnapshot:
    app_id: str
    title: str
    artist: str
    album: str
    playback_status: str


_APP_NAME_HINTS = (
    ("spotify", "Spotify"),
    ("cloudmusic", "NetEase Cloud Music"),
    ("netease", "NetEase Cloud Music"),
    ("qqmusic", "QQ Music"),
    ("kugou", "KuGou"),
    ("zunemusic", "Media Player"),
    ("chrome", "Chrome"),
    ("msedge", "Edge"),
    ("firefox", "Firefox"),
    ("foobar", "foobar2000"),
    ("potplayer", "PotPlayer"),
    ("bilibili", "Bilibili"),
)


def display_app_name(app_id: str) -> str:
    value = str(app_id or "").strip()
    lower = value.lower()
    for needle, label in _APP_NAME_HINTS:
        if needle in lower:
            return label
    if "!" in value:
        value = value.split("!", 1)[0]
    if "\\" in value:
        value = value.rsplit("\\", 1)[-1]
    if "." in value:
        parts = [part for part in value.split(".") if part]
        if parts:
            value = parts[-1]
    return value or "Media"


def format_track_line(snapshot: MediaSessionSnapshot | None) -> str:
    if snapshot is None:
        return ""
    title = str(snapshot.title or "").strip()
    artist = str(snapshot.artist or "").strip()
    if title and artist:
        return f"{artist} - {title}"
    return title or artist or display_app_name(snapshot.app_id)


def choose_display_session(sessions: Iterable[MediaSessionSnapshot]) -> MediaSessionSnapshot | None:
    items = [item for item in sessions if item is not None]
    for item in items:
        if item.playback_status == "playing":
            return item
    return items[0] if items else None


def is_media_session_supported() -> bool:
    try:
        import winsdk.windows.media.control  # noqa: F401
        return True
    except Exception:
        return False


def get_current_media_snapshot() -> MediaSessionSnapshot | None:
    return _run_async(_get_current_media_snapshot_async())


def send_media_command(command: str) -> bool:
    if command not in {"play_pause", "play", "pause", "next", "previous"}:
        return False
    return bool(_run_async(_send_media_command_async(command)))


def _run_async(awaitable):
    try:
        return asyncio.run(awaitable)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(awaitable)
        finally:
            loop.close()


async def _request_manager():
    try:
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    except Exception:
        return None
    try:
        return await GlobalSystemMediaTransportControlsSessionManager.request_async()
    except Exception:
        return None


async def _get_current_media_snapshot_async() -> MediaSessionSnapshot | None:
    manager = await _request_manager()
    if manager is None:
        return None
    sessions = []
    try:
        for session in manager.get_sessions():
            snapshot = await _snapshot_from_session(session)
            if snapshot:
                sessions.append(snapshot)
    except Exception:
        pass
    if not sessions:
        try:
            current = manager.get_current_session()
            snapshot = await _snapshot_from_session(current) if current else None
            return snapshot
        except Exception:
            return None
    return choose_display_session(sessions)


async def _send_media_command_async(command: str) -> bool:
    manager = await _request_manager()
    if manager is None:
        return False
    session = None
    try:
        sessions = list(manager.get_sessions())
        playing = [item for item in sessions if _playback_status(item) == "playing"]
        session = playing[0] if playing else (sessions[0] if sessions else None)
    except Exception:
        pass
    if session is None:
        try:
            session = manager.get_current_session()
        except Exception:
            session = None
    if session is None:
        return False
    try:
        if command == "play_pause":
            return bool(await session.try_toggle_play_pause_async())
        if command == "play":
            return bool(await session.try_play_async())
        if command == "pause":
            return bool(await session.try_pause_async())
        if command == "next":
            return bool(await session.try_skip_next_async())
        if command == "previous":
            return bool(await session.try_skip_previous_async())
    except Exception:
        return False
    return False


async def _snapshot_from_session(session) -> MediaSessionSnapshot | None:
    if session is None:
        return None
    try:
        props = await session.try_get_media_properties_async()
    except Exception:
        props = None
    try:
        app_id = str(session.source_app_user_model_id or "")
    except Exception:
        app_id = ""
    title = str(getattr(props, "title", "") or "") if props else ""
    artist = str(getattr(props, "artist", "") or "") if props else ""
    album = str(getattr(props, "album_title", "") or "") if props else ""
    status = _playback_status(session)
    if not any((title, artist, app_id)):
        return None
    return MediaSessionSnapshot(
        app_id=app_id,
        title=title,
        artist=artist,
        album=album,
        playback_status=status,
    )


def _playback_status(session) -> str:
    try:
        playback_info = session.get_playback_info()
        status = playback_info.playback_status
        name = getattr(status, "name", "")
        if name:
            return str(name).lower()
        text = str(status).lower()
        if "playing" in text:
            return "playing"
        if "paused" in text:
            return "paused"
        if "stopped" in text:
            return "stopped"
    except Exception:
        pass
    return "unknown"
