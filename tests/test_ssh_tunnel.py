import pathlib
import subprocess
import unittest
from unittest import mock

import ssh_tunnel


class SshTunnelConfigurationTest(unittest.TestCase):
    def test_defaults_target_the_ipv6_server_hostname_on_standard_ssh_port(self):
        self.assertEqual(ssh_tunnel._SSH_HOST, "server.vanillatte.cafe")
        self.assertEqual(ssh_tunnel._SSH_PORT, 22)

    def test_command_keeps_the_local_listener_ipv4_without_forcing_address_family(self):
        command = ssh_tunnel._build_ssh_command(key_path=None)

        self.assertNotIn("-6", command)
        self.assertIn(
            "127.0.0.1:9880:127.0.0.1:9880",
            command,
        )
        self.assertIn("kirby@server.vanillatte.cafe", command)
        self.assertIn("BatchMode=yes", command)
        self.assertIn("PasswordAuthentication=no", command)
        self.assertIn("KbdInteractiveAuthentication=no", command)
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertEqual(command[-1], "kirby@server.vanillatte.cafe")

    def test_explicit_key_is_passed_as_a_separate_ssh_argument(self):
        command = ssh_tunnel._build_ssh_command(key_path=r"C:\keys\bandori_key")

        key_index = command.index("-i")
        self.assertEqual(command[key_index + 1], r"C:\keys\bandori_key")
        self.assertIn("IdentitiesOnly=yes", command)

    def test_source_contains_no_password_fallback_or_runtime_package_install(self):
        source = pathlib.Path(ssh_tunnel.__file__).read_text(encoding="utf-8")

        for forbidden in ("_SSH_PASS", "ssh_password", '"pip", "install"'):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_main_gates_the_tunnel_and_keeps_the_fallback_backend_on_loopback(self):
        main_source = (
            pathlib.Path(ssh_tunnel.__file__).with_name("main.py").read_text(
                encoding="utf-8"
            )
        )

        self.assertGreaterEqual(
            main_source.count('if not bool(cfg.get("tts_enabled", False)):'),
            2,
        )
        self.assertIn('"-a", "127.0.0.1", "-p", "9880"', main_source)
        self.assertNotIn('"-a", "0.0.0.0", "-p", "9880"', main_source)


class SshTunnelLifecycleTest(unittest.TestCase):
    def setUp(self):
        ssh_tunnel._proc = None
        ssh_tunnel._watchdog_thread = None
        ssh_tunnel._stop_watchdog.clear()
        ssh_tunnel._last_error = ""

    def tearDown(self):
        ssh_tunnel._proc = None
        ssh_tunnel._watchdog_thread = None
        ssh_tunnel._stop_watchdog.set()
        ssh_tunnel._last_error = ""

    @mock.patch("ssh_tunnel.subprocess.Popen")
    @mock.patch("ssh_tunnel._port_open", return_value=True)
    def test_start_reuses_an_existing_local_forward(self, _port_open, popen):
        self.assertTrue(ssh_tunnel.start())
        popen.assert_not_called()

    @mock.patch("ssh_tunnel.time.sleep")
    @mock.patch("ssh_tunnel._port_open", side_effect=[False, True])
    @mock.patch("ssh_tunnel.subprocess.Popen")
    def test_launch_waits_until_the_local_forward_is_listening(
        self,
        popen,
        _port_open,
        _sleep,
    ):
        process = popen.return_value
        process.poll.return_value = None

        self.assertTrue(ssh_tunnel._launch_ssh(wait_timeout=1.0, key_path=None))
        self.assertIs(ssh_tunnel._proc, process)
        self.assertGreaterEqual(_port_open.call_count, 2)

    @mock.patch("ssh_tunnel._port_open", return_value=False)
    @mock.patch("ssh_tunnel.subprocess.Popen")
    def test_launch_reports_an_early_ssh_failure(self, popen, _port_open):
        process = popen.return_value
        process.poll.return_value = 255
        process.communicate.return_value = (None, "Permission denied (publickey).")

        with mock.patch("builtins.print"):
            self.assertFalse(
                ssh_tunnel._launch_ssh(wait_timeout=1.0, key_path=None)
            )
        self.assertIsNone(ssh_tunnel._proc)
        self.assertIn("public-key authentication failed", ssh_tunnel.last_error().lower())

    def test_stop_terminates_only_the_owned_process(self):
        process = mock.Mock()
        process.poll.return_value = None
        ssh_tunnel._proc = process

        ssh_tunnel.stop()

        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=4)
        process.kill.assert_not_called()
        self.assertIsNone(ssh_tunnel._proc)

    def test_stop_reaps_the_process_after_forced_termination(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="ssh", timeout=4),
            None,
        ]
        ssh_tunnel._proc = process

        ssh_tunnel.stop()

        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(process.wait.call_count, 2)
        self.assertIsNone(ssh_tunnel._proc)


if __name__ == "__main__":
    unittest.main()
