#!/usr/bin/env python3
"""Offline/disposable controller backup and recovery integration tests."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import controller_manager as ctl  # noqa: E402


def command(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True).stdout


class ControllerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.paths = ctl.Paths(
            repository=base / "project",
            home=base / "root",
            state=base / "state",
            config=base / "config",
        )
        self.paths.repository.mkdir()
        command(["git", "init", "-q", "-b", "main", str(self.paths.repository)])
        command(["git", "-C", str(self.paths.repository), "config", "user.name", "CI"])
        command(["git", "-C", str(self.paths.repository), "config", "user.email", "ci@example.invalid"])
        (self.paths.repository / ".gitignore").write_text(
            "inventory/hosts.ini\ninventory/group_vars/all/vault.yml\n", encoding="utf-8"
        )
        command(["git", "-C", str(self.paths.repository), "add", ".gitignore"])
        command(["git", "-C", str(self.paths.repository), "commit", "-q", "-m", "fixture"])
        self.sample = {
            "inventory/hosts.ini": b"[common]\nci.example.invalid\n",
            "inventory/group_vars/all/vault.yml": b"$ANSIBLE_VAULT;1.1;AES256\nfixture\n",
            "credentials/vault_pass": b"test-only-vault-pass\n",
            "ssh/ansible_ssh_key": b"fixture private key; not real\n",
            "ssh/ansible_ssh_key.pub": b"fixture public key; not real\n",
        }
        for name, data in self.sample.items():
            ctl.atomic_bytes(self.paths.target(name), data, ctl.FILES[name][2])

    def test_required_files_and_scope(self):
        self.assertEqual(len(ctl.FILES), 5)
        self.assertIn("credentials/vault_pass", ctl.FILES)
        self.assertNotIn("ssh/config", ctl.FILES)
        for name in ctl.FILES:
            self.assertTrue(self.paths.target(name).is_file())

    def test_fail_closed_missing_file(self):
        self.paths.target("credentials/vault_pass").unlink()
        with self.assertRaisesRegex(ctl.BackupError, "Missing"):
            ctl.make_archive(self.paths, Path(self.tmp.name) / "missing.tar.gz")

    def test_fail_closed_unsafe_private_permissions(self):
        path = self.paths.target("ssh/ansible_ssh_key")
        path.chmod(0o644)
        with self.assertRaisesRegex(ctl.BackupError, "permissions"):
            ctl.make_archive(self.paths, Path(self.tmp.name) / "bad.tar.gz")

    def test_fail_closed_dirty_git_tree(self):
        (self.paths.repository / "local-change.txt").write_text("uncommitted")
        with self.assertRaisesRegex(ctl.BackupError, "changes"):
            ctl.git_version(self.paths)

    def test_reject_unexpected_archive_member(self):
        dest = Path(self.tmp.name) / "invalid.tar.gz"
        with ctl.tarfile.open(dest, "w:gz") as archive:
            item = ctl.tarfile.TarInfo("../../unexpected")
            item.size = 4
            archive.addfile(item, io.BytesIO(b"bad!"))
        with self.assertRaisesRegex(ctl.BackupError, "unexpected"):
            ctl.inspect_plain_archive(dest)

    @unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"),
                         "age is required for real cryptographic test")
    def test_real_age_roundtrip_verify_restore_and_overwrite_refusal(self):
        identity = Path(self.tmp.name) / "recovery.key"
        command(["age-keygen", "-o", str(identity)])
        recipient = command(["age-keygen", "-y", str(identity)]).decode().strip()
        ctl.atomic_bytes(self.paths.recipient_file, (recipient + "\n").encode(), 0o600)
        with redirect_stdout(io.StringIO()):
            encrypted = ctl.backup(self.paths, upload=False)
            ctl.verify(self.paths, encrypted, identity)
        self.assertTrue(encrypted.read_bytes().startswith(b"age-encryption.org"))
        self.assertNotIn(b"test-only-vault-pass", encrypted.read_bytes())
        with self.assertRaisesRegex(ctl.BackupError, "clean target"):
            ctl.restore(self.paths, encrypted, identity)

        recovered = ctl.Paths(repository=Path(self.tmp.name) / "restored/project",
                              home=Path(self.tmp.name) / "restored/root")
        with redirect_stdout(io.StringIO()):
            ctl.restore(recovered, encrypted, identity)
        for name, contents in self.sample.items():
            self.assertEqual(recovered.target(name).read_bytes(), contents)
            self.assertEqual(recovered.target(name).stat().st_mode & 0o777,
                             ctl.FILES[name][2])
        self.assertFalse((recovered.home / ".ssh/config").exists())

    @unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"),
                         "age is required for real cryptographic test")
    def test_wrong_recovery_identity_refused(self):
        identity = Path(self.tmp.name) / "first.key"
        wrong = Path(self.tmp.name) / "wrong.key"
        command(["age-keygen", "-o", str(identity)])
        command(["age-keygen", "-o", str(wrong)])
        recipient = command(["age-keygen", "-y", str(identity)]).decode().strip()
        ctl.atomic_bytes(self.paths.recipient_file, (recipient + "\n").encode(), 0o600)
        with redirect_stdout(io.StringIO()):
            archive = ctl.backup(self.paths)
        with self.assertRaises(ctl.BackupError):
            ctl.verify(self.paths, archive, wrong)

    @unittest.skipUnless(shutil.which("ansible-vault") and shutil.which("ssh-keygen"),
                         "Ansible Vault required for fresh-install test")
    def test_fresh_installer_creates_real_encrypted_vault(self):
        new_paths = ctl.Paths(repository=Path(self.tmp.name) / "new-project",
                              home=Path(self.tmp.name) / "new-root")
        new_paths.repository.mkdir()
        prompts = iter(["example.invalid", ""])
        passwords = iter(["initial-pass", "sudo-pass", "test-cf-token",
                          "test-api-key", "new-strong-vault-pass", "new-strong-vault-pass"])
        with mock.patch("builtins.input", side_effect=lambda *args: next(prompts)), \
             mock.patch.object(ctl.getpass, "getpass",
                               side_effect=lambda *args: next(passwords)), \
             redirect_stdout(io.StringIO()):
            ctl.fresh(new_paths, vault_binary="ansible-vault")
        self.assertTrue(new_paths.target("inventory/group_vars/all/vault.yml")
                        .read_bytes().startswith(b"$ANSIBLE_VAULT;"))
        self.assertEqual(new_paths.target("credentials/vault_pass").read_text(),
                         "new-strong-vault-pass\n")
        self.assertTrue(new_paths.target("ssh/ansible_ssh_key").exists())
        self.assertTrue((new_paths.home / ".ssh/config").exists())
        self.assertNotIn(b"test-cf-token",
                         new_paths.target("inventory/group_vars/all/vault.yml").read_bytes())


if __name__ == "__main__":
    unittest.main()
