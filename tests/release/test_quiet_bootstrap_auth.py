#!/usr/bin/env python3
"""Check that optional discovery fallback never masks real Ansible errors."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ansible.plugins.callback.default import CallbackModule as DefaultCallback
from callback_plugins.quiet_bootstrap_auth import CallbackModule, _PROBES, _matches_register

ROOT = Path(__file__).resolve().parents[2]


def event(name, register, *, no_log=True, ignored=True, action="ansible.builtin.raw"):
    return SimpleNamespace(
        _task=SimpleNamespace(
            get_name=lambda: name,
            register=register,
            action=action,
            no_log=no_log,
            ignore_unreachable=ignored,
        ),
        _host=SimpleNamespace(get_name=lambda: "Yotta-TR"),
        _result={"unreachable": True, "msg": "do-not-print-this-sensitive-error"},
    )


class QuietBootstrapProbeTests(unittest.TestCase):
    def setUp(self):
        self.callback = CallbackModule()
        self.display = MagicMock()
        self.callback._display = self.display

    def test_all_three_expected_fallbacks_produce_neutral_messages(self):
        with patch.object(DefaultCallback, "v2_runner_on_unreachable") as parent:
            for name, (register, message) in _PROBES.items():
                with self.subTest(name=name):
                    self.display.reset_mock()
                    # Match the register representation emitted by Ansible 2.21.
                    self.callback.v2_runner_on_unreachable(
                        event(name, {register: "_task.polymorphic_result"})
                    )
                    printed = self.display.display.call_args.args[0]
                    self.assertIn("Yotta-TR", printed)
                    self.assertIn(message, printed)
                    self.assertNotIn("do-not-print-this-sensitive-error", printed)
                    self.assertNotIn("UNREACHABLE!", printed)
                    self.assertNotIn("fatal:", printed)
            parent.assert_not_called()

    def test_register_matches_both_new_and_legacy_ansible_versions(self):
        self.assertTrue(_matches_register(
            {"bootstrap_auto_key_probe": "_task.polymorphic_result"},
            "bootstrap_auto_key_probe",
        ))
        self.assertTrue(_matches_register(
            "bootstrap_auto_key_probe", "bootstrap_auto_key_probe"
        ))
        self.assertFalse(_matches_register(
            {"different_result": "_task.polymorphic_result"},
            "bootstrap_auto_key_probe",
        ))
        self.assertFalse(_matches_register(
            {"bootstrap_auto_key_probe": "x", "other": "y"},
            "bootstrap_auto_key_probe",
        ))

    def test_non_optional_and_unsafe_failure_states_use_normal_callback(self):
        name, (register, _) = next(iter(_PROBES.items()))
        cases = (
            event("Perform system update as final bootstrap operation", register),
            event("Confirm SSH reconnection before final OS upgrade", register),
            event(name, "another_result"),
            event(name, register, ignored=False),
            event(name, register, no_log=False),
            event(name, register, action="ansible.builtin.command"),
        )
        with patch.object(DefaultCallback, "v2_runner_on_unreachable") as parent:
            for result in cases:
                with self.subTest(name=result._task.get_name()):
                    self.callback.v2_runner_on_unreachable(result)
            self.assertEqual(parent.call_count, len(cases))
        self.display.display.assert_not_called()

    def test_default_output_and_public_certificate_callback_are_preserved(self):
        config = (ROOT / "ansible.cfg").read_text()
        self.assertIn("stdout_callback = quiet_bootstrap_auth", config)
        self.assertIn("callbacks_enabled = pasarguard_certificate_output", config)
        self.assertIs(CallbackModule.v2_runner_on_failed, DefaultCallback.v2_runner_on_failed)
        self.assertIs(CallbackModule.v2_runner_on_ok, DefaultCallback.v2_runner_on_ok)
        self.assertIs(CallbackModule.v2_playbook_on_stats, DefaultCallback.v2_playbook_on_stats)


if __name__ == "__main__":
    unittest.main()
