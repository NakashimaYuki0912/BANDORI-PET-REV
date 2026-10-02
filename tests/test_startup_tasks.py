import threading
import unittest

from startup_tasks import start_tts_services_async


class TtsStartupTaskTest(unittest.TestCase):
    def test_blocking_tunnel_attempt_does_not_block_startup_caller(self):
        tunnel_started = threading.Event()
        release_tunnel = threading.Event()
        backend_started = threading.Event()

        def start_tunnel():
            tunnel_started.set()
            release_tunnel.wait(timeout=2)

        thread = start_tts_services_async(
            start_tunnel=start_tunnel,
            start_fallback_backend=backend_started.set,
            is_cancelled=lambda: False,
        )

        try:
            self.assertTrue(tunnel_started.wait(timeout=1))
            self.assertTrue(thread.daemon)
            self.assertTrue(thread.is_alive())
            self.assertFalse(backend_started.is_set())
        finally:
            release_tunnel.set()
            thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertTrue(backend_started.is_set())

    def test_cancelled_start_does_not_start_fallback_backend(self):
        backend_started = threading.Event()
        cancelled = threading.Event()

        thread = start_tts_services_async(
            start_tunnel=cancelled.set,
            start_fallback_backend=backend_started.set,
            is_cancelled=cancelled.is_set,
        )
        thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertFalse(backend_started.is_set())


if __name__ == "__main__":
    unittest.main()
