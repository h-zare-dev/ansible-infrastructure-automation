"""Default Ansible output with neutral SSH discovery fallback messages."""

from __future__ import annotations

from ansible import constants as C
from ansible.plugins.callback.default import CallbackModule as DefaultCallback

DOCUMENTATION = r"""
name: quiet_bootstrap_auth
type: stdout
short_description: Preserve default output except for optional SSH probes
description:
  - Inherits the built-in default stdout callback and renders expected
    Auto Bootstrap SSH-auth fallback failures as neutral status messages.
  - Genuinely unreachable hosts still fail at Auto Bootstrap's final assert.
  - All unrelated failed or unreachable tasks use default error reporting.
extends_documentation_fragment:
  - default_callback
  - result_format_callback
requirements:
  - configured as the stdout callback in ansible.cfg
"""

_PROBES = {
    "Check marker and hardening with key-only SSH": (
        "bootstrap_auto_key_probe",
        "SSH Key did not connect; trying initial password",
    ),
    "Check hosts without working key-based access using initial password": (
        "bootstrap_auto_password_probe",
        "initial password did not connect; review final host classification",
    ),
    "Verify configured Ansible public key is already authorized for key-only hosts": (
        "bootstrap_auto_authorized_key_probe",
        "authorized-key check did not connect; review final host classification",
    ),
}


class CallbackModule(DefaultCallback):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "stdout"
    CALLBACK_NAME = "quiet_bootstrap_auth"

    def v2_runner_on_unreachable(self, result):
        task = result._task
        expected = _PROBES.get(task.get_name())
        # Temporary CI-only diagnostics to identify runtime task attributes;
        # no credentials, hosts or raw SSH errors are printed.
        import os
        if os.getenv("CI") == "true" and expected is not None:
            self._display.display(
                "CI-PROBE-CALLBACK: action=%r register=%r no_log=%r ignored=%r"
                % (
                    getattr(task, "action", None),
                    getattr(task, "register", None),
                    getattr(task, "no_log", None),
                    getattr(task, "ignore_unreachable", None),
                ),
            )
        if (
            expected is not None
            and getattr(task, "register", None) == expected[0]
            and getattr(task, "action", None) in ("raw", "ansible.builtin.raw")
            and getattr(task, "no_log", False) is True
            and getattr(task, "ignore_unreachable", False) is True
        ):
            self._display.display(
                "probe unavailable: [%s] (%s)"
                % (result._host.get_name(), expected[1]),
                color=C.COLOR_SKIP,
            )
            return

        # No other SSH, reboot, update or final-assert failures are masked.
        super().v2_runner_on_unreachable(result)
