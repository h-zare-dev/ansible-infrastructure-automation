#!/usr/bin/env python3
"""Contract checks for read-only PasarGuard certificate inspection."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class PasarguardCertificateContracts(unittest.TestCase):
    def test_certificate_view_never_copies_or_outputs_private_key(self):
        play = load("playbooks/operations/show-pasarguard-certificate.yml")[0]
        self.assertEqual(play["hosts"], "pasarguard_nodes")
        self.assertFalse(play["gather_facts"])
        self.assertTrue(play["become"])
        self.assertIn("../../roles/pasarguard/defaults/main.yml", play["vars_files"])
        tasks = play["tasks"]
        self.assertTrue(any("ansible.builtin.stat" in t for t in tasks))
        self.assertTrue(any("ansible.builtin.assert" in t for t in tasks))
        self.assertFalse(any(
            any(op in t for op in (
                "ansible.builtin.fetch",
                "ansible.builtin.copy",
                "ansible.builtin.slurp",
                "ansible.builtin.shell",
                "ansible.builtin.template",
            ))
            for t in tasks
        ))
        commands = [t["ansible.builtin.command"] for t in tasks if "ansible.builtin.command" in t]
        self.assertEqual(len(commands), 2)
        for command in commands:
            argv = command["argv"]
            self.assertEqual(argv[:2], ["openssl", "x509"])
            self.assertIn("{{ pasarguard_cert_path }}", argv)
        self.assertIn("-outform", commands[1]["argv"])
        self.assertIn("PEM", commands[1]["argv"])
        self.assertIn("-fingerprint", commands[0]["argv"])
        self.assertIn("-dates", commands[0]["argv"])
        self.assertTrue(all(t["changed_when"] is False for t in tasks if "ansible.builtin.command" in t))
        self.assertFalse(any("ansible.builtin.fetch" in t for t in load("roles/pasarguard/tasks/main.yml")))

    def test_installer_keeps_api_key_out_of_task_logs(self):
        roles = load("roles/pasarguard/tasks/main.yml")
        self.assertIn("common_api_key", roles[0]["ansible.builtin.shell"])
        self.assertTrue(roles[0]["no_log"])
        self.assertFalse(any(t.get("no_log") for t in roles[1:]))

    def test_certificate_path_is_shared_default_without_controller_cache(self):
        defaults = load("roles/pasarguard/defaults/main.yml")
        self.assertEqual(defaults["pasarguard_cert_path"], "/var/lib/pg-node/certs/ssl_cert.pem")
        group_vars = load("inventory/group_vars/all/vars.yml")
        self.assertNotIn("pasarguard_cert_destination_dir", group_vars)
        assert "pasarguard_cert_destination_dir" not in (ROOT / "roles/pasarguard/tasks/main.yml").read_text()

    def test_abuse_firewall_script_path_is_not_duplicated(self):
        tasks = load("roles/abuse_firewall/tasks/main.yml")
        handler = load("roles/abuse_firewall/handlers/main.yml")
        cron = next(t for t in tasks if "ansible.builtin.cron" in t)
        template = next(t for t in tasks if "ansible.builtin.template" in t)
        self.assertEqual(template["ansible.builtin.template"]["dest"], "{{ abuse_firewall_script_path }}")
        self.assertEqual(cron["ansible.builtin.cron"]["job"], "{{ abuse_firewall_script_path }}")
        self.assertEqual(handler[0]["ansible.builtin.command"]["argv"], ["{{ abuse_firewall_script_path }}"])


if __name__ == "__main__":
    unittest.main()
