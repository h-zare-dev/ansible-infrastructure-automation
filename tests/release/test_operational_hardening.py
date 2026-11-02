#!/usr/bin/env python3
"""Offline contract and negative-case tests: no production access or fault injection."""
from __future__ import annotations

import copy
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: str):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def load_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require_bounded_apt_wait(tasks: list[dict]) -> None:
    """Reject the unsafe policy of immediately failing on a transient APT lock."""
    found = 0
    for task in tasks:
        if "ansible.builtin.apt" not in task:
            continue
        found += 1
        timeout = task["ansible.builtin.apt"].get("lock_timeout")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 60 or timeout > 600:
            raise AssertionError(f"APT task {task['name']!r} has unsafe lock_timeout={timeout!r}")
    if not found:
        raise AssertionError("No APT tasks found")


class OperationalFailureContracts(unittest.TestCase):
    def test_apt_lock_waits_are_bounded_on_maintenance_tasks(self):
        for path in (
            "roles/system_update/tasks/debian.yml",
            "roles/security_updates/tasks/main.yml",
        ):
            with self.subTest(path=path):
                require_bounded_apt_wait(load_yaml(path))

    def test_negative_case_missing_lock_timeout_is_rejected(self):
        tasks = copy.deepcopy(load_yaml("roles/system_update/tasks/debian.yml"))
        first_apt = next(t for t in tasks if "ansible.builtin.apt" in t)
        first_apt["ansible.builtin.apt"].pop("lock_timeout", None)
        with self.assertRaisesRegex(AssertionError, "lock_timeout"):
            require_bounded_apt_wait(tasks)

    def test_apt_locks_are_never_deleted_or_force_killed(self):
        for path in ("roles/system_update/tasks/debian.yml", "roles/security_updates/tasks/main.yml"):
            content = load_text(path)
            for forbidden in ("rm /var/lib/dpkg/lock", "killall apt", "fuser -k", "pkill apt"):
                self.assertNotIn(forbidden, content)

    def test_bootstrap_reconnect_is_before_last_os_update_and_fails_closed(self):
        bootstrap = load_yaml("playbooks/bootstrap.yml")
        self.assertEqual([p["hosts"] for p in bootstrap], ["{{ bootstrap_host }}"] * 2)
        self.assertEqual(bootstrap[0]["roles"], ["controller_known_hosts"])
        self.assertEqual(bootstrap[1]["roles"], ["ssh_security", "cloudflare_dns", "controller_ssh_config"])
        steps = bootstrap[1]["tasks"]
        self.assertEqual(steps[0].get("ansible.builtin.meta"), "flush_handlers")
        self.assertEqual(steps[1].get("ansible.builtin.meta"), "reset_connection")
        wait = steps[2]["ansible.builtin.wait_for_connection"]
        self.assertGreaterEqual(wait["timeout"], 120)
        self.assertGreater(wait["connect_timeout"], 0)
        self.assertFalse(steps[2].get("ignore_errors", False))
        self.assertNotIn("failed_when", steps[2])
        self.assertEqual(steps[-1]["ansible.builtin.include_role"]["name"], "system_update")
        self.assertTrue(bootstrap[1]["vars"]["system_update_reboot"])

    def test_reboot_requires_positive_bounded_timeouts_and_explicit_flag(self):
        defaults = load_yaml("roles/system_update/defaults/main.yml")
        for name in ("system_update_reboot_timeout", "system_update_connect_timeout", "system_update_post_reboot_delay"):
            self.assertIsInstance(defaults[name], int)
            self.assertGreater(defaults[name], 0)
        main = load_yaml("roles/system_update/tasks/main.yml")
        reboot = next(t for t in main if "ansible.builtin.reboot" in t)
        self.assertIn("system_update_reboot | bool", reboot["when"])
        self.assertIn("system_update_reboot_needed | default(false) | bool", reboot["when"])
        self.assertEqual(reboot["ansible.builtin.reboot"]["reboot_timeout"], "{{ system_update_reboot_timeout }}")

    def test_release_api_failures_do_not_silently_fall_back(self):
        cases = (
            ("roles/floatip_manager/tasks/main.yml", [200, 404]),
            ("roles/port_forward_manager/tasks/main.yml", 200),
        )
        for path, expected_codes in cases:
            with self.subTest(path=path):
                tasks = load_yaml(path)
                release = next(t for t in tasks if "ansible.builtin.uri" in t)
                self.assertEqual(release["ansible.builtin.uri"]["status_code"], expected_codes)
                self.assertFalse(release.get("ignore_errors", False))
                self.assertFalse(release.get("failed_when", False))
                stable = next(t for t in tasks if t["name"].startswith("Validate stable") or t["name"] == "Validate latest release reference")
                checks = " ".join(stable["ansible.builtin.assert"]["that"])
                self.assertIn("tag_name", checks)
                self.assertIn("prerelease", checks)
                self.assertIn("draft", checks)

    def test_documentation_matches_current_bootstrap_and_ssh_risk(self):
        agents = load_text("AGENTS.md")
        self.assertIn("clearing **all entries**", agents)
        self.assertIn("**last** run `system_update`", agents)
        self.assertIn("host_key_checking = False", agents)
        self.assertIn("verify new SSH host keys independently", agents)
        known = load_yaml("roles/controller_known_hosts/tasks/main.yml")
        self.assertEqual(known[0]["delegate_to"], "localhost")
        self.assertTrue(known[0]["run_once"])
        self.assertEqual(known[0]["block"][-1]["ansible.builtin.copy"]["content"], "")
        self.assertIn("host_key_checking = False", load_text("ansible.cfg"))
        self.assertIn("checksum/signature assets", agents)


class CISecretScanningContracts(unittest.TestCase):
    def test_secret_scan_is_pinned_and_mandatory(self):
        workflow = load_yaml(".github/workflows/ci.yml")
        scan = workflow["jobs"]["secret-scan"]
        actions = [step["uses"] for step in scan["steps"] if "uses" in step]
        self.assertTrue(any(re.fullmatch(r"gitleaks/gitleaks-action@[0-9a-f]{40}", x) for x in actions))
        self.assertIn("secret-scan", workflow["jobs"]["ci-gate"]["needs"])
        env = workflow["jobs"]["ci-gate"]["steps"][0]["env"]
        self.assertIn("SECRET_SCAN_RESULT", env)
        script = workflow["jobs"]["ci-gate"]["steps"][0]["run"]
        self.assertIn('if [[ "$SECRET_SCAN_RESULT" != "success" ]]', script)
        self.assertEqual(scan["steps"][-1]["env"]["GITLEAKS_ENABLE_COMMENTS"], "false")


if __name__ == "__main__":
    unittest.main()
