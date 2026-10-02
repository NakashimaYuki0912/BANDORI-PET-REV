"""Background startup tasks that must not delay the pet window."""

from __future__ import annotations

import threading
from collections.abc import Callable


def start_tts_services_async(
    *,
    start_tunnel: Callable[[], object],
    start_fallback_backend: Callable[[], object],
    is_cancelled: Callable[[], bool],
) -> threading.Thread:
    """Start the tunnel first, then the local fallback, without blocking UI."""

    def run() -> None:
        start_tunnel()
        if not is_cancelled():
            start_fallback_backend()

    thread = threading.Thread(
        target=run,
        name="bandoripet-tts-startup",
        daemon=True,
    )
    thread.start()
    return thread
