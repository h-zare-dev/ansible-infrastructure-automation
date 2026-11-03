# This aggregate callback adds raw public PEM lines while preserving Ansible's
# default stdout callback and all normal error reporting.
from __future__ import annotations

import re

from ansible.plugins.callback import CallbackBase

DOCUMENTATION = r"""
name: pasarguard_certificate_output
type: aggregate
short_description: Print public PasarGuard X.509 certificates with real line breaks
description:
  - Only processes the two explicitly named public certificate inspection tasks.
  - Formats valid public X.509 certificates without JSON backslash escaping.
  - Does not print private keys or write certificate files.
"""

_METADATA_TASK = "Read certificate validity and SHA256 fingerprint on the node"
_PEM_TASK = "Extract public certificate PEM on the node"
_PEM_BODY = re.compile(r"[A-Za-z0-9+/]+={0,2}\Z")


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "pasarguard_certificate_output"
    CALLBACK_NEEDS_ENABLED = True

    def v2_runner_on_ok(self, result):
        task = result._task
        name = task.get_name()
        if name not in (_METADATA_TASK, _PEM_TASK):
            return
        if task.action not in ("command", "ansible.builtin.command"):
            return

        data = result._result
        if data.get("failed") or data.get("_ansible_no_log"):
            return
        stdout = data.get("stdout")
        if not isinstance(stdout, str) or not stdout.strip():
            return

        host = result._host.get_name()

        if name == _METADATA_TASK:
            lines = stdout.strip().splitlines()
            prefixes = ("notBefore=", "notAfter=", "sha256 Fingerprint=")
            if len(lines) != 3 or not all(line.startswith(prefixes) for line in lines):
                return
            self._display.display(
                "\nPasarGuard certificate on " + host + ":\n" + "\n".join(lines) + "\n"
            )
            return

        lines = stdout.strip().splitlines()
        if (
            len(lines) < 3
            or lines[0] != "-----BEGIN CERTIFICATE-----"
            or lines[-1] != "-----END CERTIFICATE-----"
            or not all(_PEM_BODY.fullmatch(line) and len(line) <= 64 for line in lines[1:-1])
        ):
            self._display.warning(
                "PasarGuard public PEM did not match the expected format; "
                "refusing to print potentially unsafe content."
            )
            return

        self._display.display(
            "\n========== Public certificate: " + host + " ==========\n"
            + "\n".join(lines)
            + "\n========== End public certificate ==========\n"
        )
