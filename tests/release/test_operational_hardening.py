#!/usr/bin/env python3
"""Offline contract and negative-case tests: no production access or fault injection."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
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
        self.assertEqual([item["role"] if isinstance(item, dict) else item for item in bootstrap[0]["roles"]], ["controller_known_hosts"])
        self.assertIn("bootstrap_auto_mode", bootstrap[0]["roles"][0]["when"])
        self.assertEqual(bootstrap[1]["roles"], ["ssh_security", "cloudflare_dns", "controller_ssh_config"])
        steps = bootstrap[1]["tasks"]
        self.assertEqual(steps[0].get("ansible.builtin.meta"), "flush_handlers")
        self.assertEqual(steps[1].get("ansible.builtin.meta"), "reset_connection")
        wait = steps[2]["ansible.builtin.wait_for_connection"]
        self.assertGreaterEqual(wait["timeout"], 120)
        self.assertGreater(wait["connect_timeout"], 0)
        self.assertFalse(steps[2].get("ignore_errors", False))
        self.assertNotIn("failed_when", steps[2])
        self.assertEqual(steps[-2]["ansible.builtin.include_role"]["name"], "system_update")
        self.assertEqual(steps[-1]["ansible.builtin.copy"]["dest"], "{{ bootstrap_marker_path }}")
        self.assertEqual(steps[-1]["ansible.builtin.copy"]["content"], "{{ bootstrap_marker_content }}")
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
        self.assertIn("clears all controller-user `known_hosts` entries", agents)
        self.assertIn("run `system_update`", agents)
        self.assertIn("Marker is written **only after**", agents)
        self.assertIn("host_key_checking = False", agents)
        self.assertIn("verify host fingerprints independently", agents)
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


class SequentialMaintenanceReachabilityTests(unittest.TestCase):
    PLAYBOOK_CASES = (
        ("security-updates", "security_updates"),
        ("system-update", "system_update"),
    )

    def test_rolling_maintenance_preflight_preserves_serial_and_reports_skips(self):
        for playbook_name, role_name in self.PLAYBOOK_CASES:
            with self.subTest(playbook=playbook_name):
                plays = load_yaml(f"playbooks/operations/{playbook_name}.yml")
                self.assertEqual(len(plays), 3)
                discovery, update, report = plays
                self.assertEqual(discovery["hosts"], "all")
                self.assertFalse(discovery["gather_facts"])
                self.assertNotIn("serial", discovery)
                probe = discovery["tasks"][0]
                self.assertIn("ansible.builtin.wait_for_connection", probe)
                self.assertTrue(probe["ignore_errors"])
                self.assertTrue(probe["ignore_unreachable"])
                self.assertFalse(probe["changed_when"])
                self.assertIn(f"__{role_name}_reachable", str(discovery["tasks"]))
                self.assertIn(f"__{role_name}_unavailable", str(discovery["tasks"]))
                self.assertIn(f"__{role_name}_reachable", update["hosts"])
                self.assertIn("all:!all", update["hosts"])
                self.assertEqual(update["serial"], 1)
                self.assertFalse(update["gather_facts"])
                self.assertEqual(update["roles"], [role_name])
                self.assertIn("ansible.builtin.wait_for_connection", update["pre_tasks"][0])
                self.assertTrue(update["pre_tasks"][0]["ignore_unreachable"])
                self.assertTrue(update["pre_tasks"][0]["ignore_errors"])
                self.assertEqual(update["pre_tasks"][2]["ansible.builtin.meta"], "end_host")
                self.assertIn("ansible.builtin.setup", update["pre_tasks"][3])
                self.assertEqual(report["hosts"], "all")
                self.assertIn(f"__{role_name}_unavailable", str(report["tasks"][-1]))
                self.assertTrue(all(t["run_once"] and t["delegate_to"] == "localhost" for t in report["tasks"]))
                self.assertNotIn("ignore_errors", update)
                self.assertNotIn("ignore_unreachable", update)

                if role_name == "system_update":
                    self.assertIs(update["vars"]["system_update_reboot"], True)

    @unittest.skipUnless(shutil.which("ansible-playbook"), "Ansible only available in CI")
    def test_real_ansible_offline_middle_does_not_block_remaining_hosts(self):
        # Use the real three-play production control flow with a harmless
        # debug task in place of each role. No APT, reboot, or SSH to
        # production. Offline host uses only loopback port 1.
        for playbook_name, _ in self.PLAYBOOK_CASES:
            with self.subTest(playbook=playbook_name):
                with tempfile.TemporaryDirectory() as tmp:
                    tmpdir = Path(tmp)
                    (tmpdir / "hosts.ini").write_text(
                        chr(10).join([
                            "[canary]",
                            "online_first ansible_connection=local",
                            "offline_middle ansible_connection=ssh ansible_host=127.0.0.1 ansible_port=1 "
                            "ansible_ssh_common_args='-o StrictHostKeyChecking=no -o ConnectTimeout=1'",
                            "online_last ansible_connection=local",
                        ]) + chr(10),
                        encoding="utf-8",
                    )
                    plays = copy.deepcopy(load_yaml(f"playbooks/operations/{playbook_name}.yml"))
                    plays[1]["roles"] = []
                    plays[1]["pre_tasks"][-1] = {
                        "name": "Skip facts in isolated fixture",
                        "ansible.builtin.debug": {"msg": "fixture facts skipped"},
                    }
                    plays[1]["tasks"] = [{
                        "name": "Record fixture update for each eligible host",
                        "ansible.builtin.debug": {"msg": "FIXTURE_UPDATED_{{ inventory_hostname }}"},
                    }]
                    plays[1]["become"] = False
                    (tmpdir / "fixture.yml").write_text(
                        yaml.safe_dump(plays, sort_keys=False), encoding="utf-8"
                    )
                    env = os.environ.copy()
                    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
                    env["ANSIBLE_NOCOLOR"] = "1"
                    result = subprocess.run(
                        ["ansible-playbook", "-i", str(tmpdir / "hosts.ini"),
                         str(tmpdir / "fixture.yml")],
                        capture_output=True,
                        text=True,
                        timeout=100,
                        env=env,
                        cwd=str(ROOT),
                        check=False,
                    )
                    output = result.stdout + result.stderr
                    self.assertIn("FIXTURE_UPDATED_online_first", output)
                    self.assertIn("FIXTURE_UPDATED_online_last", output)
                    self.assertNotIn("FIXTURE_UPDATED_offline_middle", output)
                    self.assertIn("offline_middle", output)
                    self.assertIn("Report incomplete fleet", output)
                    self.assertNotEqual(result.returncode, 0,
                        "Skipped hosts must be reported after the rest finish")




if __name__ == "__main__":
    unittest.main()
