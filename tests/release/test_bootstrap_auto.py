#!/usr/bin/env python3
"""Offline automatic-bootstrap and migration safety checks."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class MarkerProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.marker = Path(self.tmp.name) / "ansible-bootstrap-complete"
        self.hardening = Path(self.tmp.name) / "00-security-hardening.conf"
        shared = load("playbooks/vars/bootstrap-marker.yml")
        self.probe_script = shared["bootstrap_probe_command"]
        self.probe_script = self.probe_script.replace(
            shared["bootstrap_marker_path"], str(self.marker)
        ).replace(shared["bootstrap_hardening_path"], str(self.hardening))

    def probe(self):
        result = subprocess.run(
            ["/bin/sh", "-c", self.probe_script],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def test_new_host_has_no_marker_or_hardening(self):
        self.assertEqual(self.probe(), "NEW")

    def test_valid_marker_always_skips_bootstrap(self):
        self.marker.write_text("completed\n")
        self.assertEqual(self.probe(), "MARKED")

    def test_half_written_marker_fails_closed(self):
        self.marker.write_text("partial\n")
        self.assertEqual(self.probe(), "INVALID")

    def test_empty_marker_fails_closed(self):
        self.marker.touch()
        self.assertEqual(self.probe(), "INVALID")

    def test_broken_marker_symlink_fails_closed(self):
        self.marker.symlink_to(self.marker.parent / "missing")
        self.assertEqual(self.probe(), "INVALID")

    def test_valid_content_symlink_is_also_invalid(self):
        source = self.marker.parent / "original"
        source.write_text("completed\n")
        self.marker.symlink_to(source)
        self.assertEqual(self.probe(), "INVALID")

    def test_hardened_old_host_is_not_bootstrapped(self):
        self.hardening.write_text(
            "PermitRootLogin prohibit-password\n"
            "PasswordAuthentication no\n"
            "PubkeyAuthentication yes\n"
        )
        self.assertEqual(self.probe(), "HARDENED")

    def test_unknown_hardening_fails_closed(self):
        self.hardening.write_text("PasswordAuthentication yes\n")
        self.assertEqual(self.probe(), "HARDENING_UNKNOWN")

    def test_invalid_marker_outweighs_hardening(self):
        self.marker.write_text("wrong\n")
        self.hardening.write_text(
            "PasswordAuthentication no\nPubkeyAuthentication yes\n"
        )
        self.assertEqual(self.probe(), "INVALID")

    def test_probe_is_read_only(self):
        before = list(Path(self.tmp.name).iterdir())
        self.probe()
        self.assertEqual(before, list(Path(self.tmp.name).iterdir()))


class BootstrapPlaybookContracts(unittest.TestCase):
    def test_auto_discovers_all_hosts_without_inventory_group_edit(self):
        auto = load("playbooks/bootstrap-auto.yml")
        self.assertEqual(auto[0]["hosts"], "all")
        self.assertFalse(auto[0]["gather_facts"])
        self.assertEqual(auto[0]["serial"], 1)
        self.assertEqual(auto[1]["ansible.builtin.import_playbook"], "bootstrap.yml")
        self.assertEqual(auto[1]["vars"]["bootstrap_host"], "__bootstrap_auto_pending")
        self.assertTrue(auto[1]["vars"]["bootstrap_auto_mode"])
        self.assertEqual(auto[2]["hosts"], "all")
        self.assertTrue(all(t.get("run_once") and t.get("delegate_to") == "localhost" for t in auto[2]["tasks"]))
        self.assertNotIn("bootstrap_candidates", read("inventory/hosts.example.ini"))

    def test_only_explicit_fresh_candidates_may_run(self):
        tasks = load("playbooks/bootstrap-auto.yml")[0]["tasks"]
        pending = next(
            task for task in tasks
            if task.get("ansible.builtin.group_by", {}).get("key")
            == "__bootstrap_auto_pending"
        )
        self.assertIn("bootstrap_auto_status == 'candidate'", pending["when"])
        self.assertIn("bootstrap_auto_discover_only", " ".join(pending["when"]))
        self.assertFalse(pending["changed_when"])

    def test_probe_authentication_isolated_and_secrets_hidden(self):
        tasks = load("playbooks/bootstrap-auto.yml")[0]["tasks"]
        probes = [task for task in tasks if "ansible.builtin.raw" in task]
        self.assertEqual(len(probes), 2)
        self.assertEqual(probes[0]["vars"]["ansible_password"], "")
        self.assertIn("vault_ansible_password", probes[1]["vars"]["ansible_password"])
        self.assertIn("ControlPath=none", probes[0]["vars"]["ansible_ssh_extra_args"])
        self.assertIn("ControlPath=none", probes[1]["vars"]["ansible_ssh_extra_args"])
        self.assertIn("PubkeyAuthentication=no", probes[1]["vars"]["ansible_ssh_extra_args"])
        self.assertIn("bootstrap_auto_key_code", probes[1]["when"])
        self.assertTrue(all(t["no_log"] and t["ignore_unreachable"] for t in probes))
        self.assertTrue(all(not t["changed_when"] for t in probes))
        expr = next(
            t for t in tasks if t["name"] == "Classify host without changing it"
        )["ansible.builtin.set_fact"]["bootstrap_auto_status"]
        for state in (
            "managed", "candidate", "needs_adoption", "invalid_marker",
            "review_hardening", "managed_key_unavailable",
            "key_only_unmanaged", "unreachable",
        ):
            self.assertIn(state, expr)

    def test_adoption_requires_hardening_and_key_only_access(self):
        adopt = load("playbooks/operations/bootstrap-adopt-existing.yml")
        self.assertEqual(len(adopt), 1)
        self.assertEqual(adopt[0]["hosts"], "all")
        self.assertEqual(adopt[0]["serial"], 1)
        tasks = adopt[0]["tasks"]
        self.assertEqual(tasks[0]["vars"]["ansible_password"], "")
        self.assertTrue(tasks[0]["no_log"])
        copy_task = next(t for t in tasks if "ansible.builtin.copy" in t)
        self.assertIn("bootstrap_adopt_status == 'HARDENED'", copy_task["when"])
        self.assertIn("bootstrap_adopt_dry_run", " ".join(copy_task["when"]))
        self.assertEqual(copy_task["ansible.builtin.copy"]["mode"], "0644")
        self.assertNotIn("system_update", read("playbooks/operations/bootstrap-adopt-existing.yml"))

    def test_manual_bootstrap_records_success_only_after_update(self):
        bootstrap = load("playbooks/bootstrap.yml")
        self.assertEqual(bootstrap[1]["serial"], 1)
        self.assertIn("bootstrap_auto_mode", bootstrap[0]["roles"][0]["when"])
        tasks = bootstrap[1]["tasks"]
        self.assertEqual(tasks[-2]["ansible.builtin.include_role"]["name"], "system_update")
        self.assertEqual(tasks[-1]["ansible.builtin.copy"]["dest"], "{{ bootstrap_marker_path }}")
        self.assertEqual(tasks[-1]["ansible.builtin.copy"]["content"], "{{ bootstrap_marker_content }}")
        self.assertEqual(tasks[-1]["ansible.builtin.copy"]["mode"], "0644")
        self.assertIn("not ansible_check_mode", tasks[-1]["when"])

    def test_auto_mode_skips_global_known_hosts_reset(self):
        bootstrap = load("playbooks/bootstrap.yml")
        first = bootstrap[0]["roles"][0]
        self.assertIn("not", first["when"])
        self.assertIn("bootstrap_auto_mode", first["when"])
        self.assertNotIn("controller_known_hosts", read("playbooks/bootstrap-auto.yml"))


if __name__ == "__main__":
    unittest.main()
