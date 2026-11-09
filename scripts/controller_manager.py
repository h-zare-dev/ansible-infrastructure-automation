#!/usr/bin/env python3
"""Local-only Ansible controller backup, recovery and setup.

No production hosts are contacted. Secrets are never logged. Private content
is encrypted using an external age recipient before it leaves tmpfs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid

FORMAT = 1
MAX_FILE = 8 * 1024 * 1024
TELEGRAM_PART = 45 * 1024 * 1024
DEFAULT_REPO = Path("/root/ansible-project")
DEFAULT_HOME = Path("/root")
DEFAULT_STATE = Path("/var/lib/ansible-controller-backup")
DEFAULT_CONFIG = Path("/etc/ansible-controller-backup")
FILES = {
    "inventory/hosts.ini": ("repository", "inventory/hosts.ini", 0o644),
    "inventory/group_vars/all/vault.yml": (
        "repository", "inventory/group_vars/all/vault.yml", 0o600
    ),
    "credentials/vault_pass": ("home", ".ansible/vault_pass", 0o600),
    "ssh/ansible_ssh_key": ("home", ".ssh/ansible_ssh_key", 0o600),
    "ssh/ansible_ssh_key.pub": ("home", ".ssh/ansible_ssh_key.pub", 0o644),
}


class BackupError(Exception):
    pass


class Paths:
    def __init__(self, repository=DEFAULT_REPO, home=DEFAULT_HOME,
                 state=DEFAULT_STATE, config=DEFAULT_CONFIG):
        self.repository = Path(repository)
        self.home = Path(home)
        self.state = Path(state)
        self.config = Path(config)

    def target(self, name):
        root, suffix, _ = FILES[name]
        return (self.repository if root == "repository" else self.home) / suffix

    @property
    def recipient_file(self):
        return self.config / "age-recipient.txt"

    @property
    def telegram_file(self):
        return self.config / "telegram.json"

    @property
    def archives(self):
        return self.state / "archives"


def ensure_private_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise BackupError("Unsafe backup directory: " + str(path))
    path.chmod(0o700)


def require_regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise BackupError("Missing or unsafe regular file: " + str(path))
    if path.stat().st_size > MAX_FILE:
        raise BackupError("File exceeds configured safety limit: " + str(path))
    if path.stat().st_nlink != 1:
        raise BackupError("Refusing hard-linked private file: " + str(path))


def atomic_bytes(path, data, mode):
    path = Path(path)
    ensure_private_dir(path.parent)
    if path.is_symlink():
        raise BackupError("Refusing symlink destination: " + str(path))
    temp = path.parent / (".new-" + uuid.uuid4().hex)
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def executable(name):
    tool = shutil.which(name)
    if tool is None:
        raise BackupError("Required command not installed: " + name)
    return tool


def run_checked(args, *, env=None, input_data=None):
    result = subprocess.run(args, input=input_data, capture_output=True,
                            env=env, check=False)
    if result.returncode:
        raise BackupError("Local command failed: " + Path(args[0]).name)
    return result.stdout


def git_version(paths):
    try:
        branch = run_checked(["git", "-C", str(paths.repository),
                              "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        commit = run_checked(["git", "-C", str(paths.repository),
                              "rev-parse", "HEAD"]).decode().strip()
        if branch != "main":
            raise BackupError("Backup requires Production branch main; got " + branch)
        if run_checked(["git", "-C", str(paths.repository),
                        "status", "--porcelain", "--untracked-files=normal"]).strip():
            raise BackupError("Working tree has changes; inspect local edits first")
        return commit
    except UnicodeDecodeError as exc:
        raise BackupError("Invalid Git metadata") from exc


def load_recipient(paths):
    require_regular(paths.recipient_file)
    recipient = paths.recipient_file.read_text(encoding="utf-8").strip()
    if not recipient.startswith("age1") or len(recipient) < 25:
        raise BackupError("Invalid age recipient file")
    return recipient


def make_archive(paths, dest):
    entries = {}
    for name in FILES:
        target = paths.target(name)
        require_regular(target)
        if target.stat().st_mode & 0o077 and name in (
            "inventory/group_vars/all/vault.yml", "credentials/vault_pass",
            "ssh/ansible_ssh_key"
        ):
            raise BackupError("Private file permissions are too broad: " + str(target))
        data = target.read_bytes()
        entries[name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "mode": FILES[name][2],
        }
    manifest = {
        "format": FORMAT,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": "h-zare-dev/ansible-infrastructure-automation",
        "git_commit": git_version(paths),
        "files": entries,
    }
    with tarfile.open(dest, "w:gz") as archive:
        blob = json.dumps(manifest, sort_keys=True).encode("utf-8")
        header = tarfile.TarInfo("manifest.json")
        header.size, header.mode = len(blob), 0o600
        archive.addfile(header, io.BytesIO(blob))
        for name, entry in entries.items():
            data = paths.target(name).read_bytes()
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise BackupError("Source changed while being archived: " + name)
            header = tarfile.TarInfo("payload/" + name)
            header.size, header.mode = len(data), entry["mode"]
            archive.addfile(header, io.BytesIO(data))
    return manifest


def backup(paths, *, upload=False):
    recipient = load_recipient(paths)
    ensure_private_dir(paths.archives)
    executable("age")
    # /run is tmpfs on supported Ubuntu hosts; never place plaintext in /tmp
    with tempfile.TemporaryDirectory(prefix="controller-backup-", dir="/run") as tmp:
        os.chmod(tmp, 0o700)
        plain = Path(tmp) / "payload.tar.gz"
        manifest = make_archive(paths, plain)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = "ansible-controller-" + stamp + ".tar.gz.age"
        final = paths.archives / filename
        if final.exists():
            raise BackupError("Archive already exists: " + str(final))
        partial = paths.archives / (filename + "." + uuid.uuid4().hex + ".partial")
        try:
            run_checked(["age", "-r", recipient, "-o", str(partial), str(plain)])
            os.chmod(partial, 0o600)
            os.replace(partial, final)
        finally:
            partial.unlink(missing_ok=True)
    if upload:
        telegram_upload(final, paths.telegram_file)
    print("Encrypted backup: " + str(final))
    print("Git commit: " + manifest["git_commit"])
    print("Upload: " + ("confirmed" if upload else "not requested"))
    return final


def telegram_upload(archive, telegram_file):
    require_regular(telegram_file)
    if telegram_file.stat().st_mode & 0o077:
        raise BackupError("Telegram credentials must be mode 0600")
    config = json.loads(telegram_file.read_text(encoding="utf-8"))
    token = config.get("bot_token", "")
    chat_id = str(config.get("chat_id", ""))
    if not token or not chat_id:
        raise BackupError("Telegram credentials are missing")
    count = (archive.stat().st_size + TELEGRAM_PART - 1) // TELEGRAM_PART
    with archive.open("rb") as stream:
        for index in range(count):
            data = stream.read(TELEGRAM_PART)
            name = archive.name if count == 1 else (
                archive.name + ".part" + str(index + 1).zfill(3)
            )
            marker = uuid.uuid4().hex
            fields = [
                (f"--{marker}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n"
                 f"\r\n{chat_id}\r\n").encode(),
                (f"--{marker}\r\nContent-Disposition: form-data; name=\"caption\"\r\n"
                 f"\r\nAnsible controller backup {index+1}/{count}\r\n").encode(),
                (f"--{marker}\r\nContent-Disposition: form-data; name=\"document\"; "
                 f"filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n"
                 f"\r\n").encode() + data + b"\r\n",
                f"--{marker}--\r\n".encode(),
            ]
            body = b"".join(fields)
            # Never emit the token-bearing URL, HTTP exception or response.
            request = urllib.request.Request(
                "https://api.telegram.org/bot" + token + "/sendDocument",
                data=body, headers={"Content-Type": "multipart/form-data; boundary=" + marker},
                method="POST",
            )
            sent = False
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=180) as response:
                        reply = json.loads(response.read(256 * 1024))
                        sent = response.status == 200 and reply.get("ok") is True
                except Exception:
                    sent = False
                if sent:
                    break
                if attempt != 2:
                    time.sleep(2 * (attempt + 1))
            if not sent:
                raise BackupError(
                    "Telegram delivery failed at part " + str(index + 1) +
                    "; encrypted local backup was retained"
                )
            print("Telegram part confirmed: " + str(index + 1) + "/" + str(count))


def inspect_plain_archive(plain):
    result = {}
    with tarfile.open(plain, "r:gz") as archive:
        names = [item.name for item in archive.getmembers()]
        expected = {"manifest.json"} | {"payload/" + key for key in FILES}
        if set(names) != expected or len(names) != len(expected):
            raise BackupError("Archive has unexpected, duplicate or missing entries")
        if any(not item.isfile() or item.size > MAX_FILE for item in archive):
            raise BackupError("Archive contains unsafe file types or sizes")
        manifest = json.load(archive.extractfile("manifest.json"))
        if (manifest.get("format") != FORMAT or
            manifest.get("repository") != "h-zare-dev/ansible-infrastructure-automation" or
            set(manifest.get("files", {})) != set(FILES)):
            raise BackupError("Unknown backup manifest format")
        for name in FILES:
            info = manifest["files"][name]
            data = archive.extractfile("payload/" + name).read(MAX_FILE + 1)
            if (len(data) > MAX_FILE or len(data) != info.get("size") or
                hashlib.sha256(data).hexdigest() != info.get("sha256")):
                raise BackupError("Archive integrity mismatch: " + name)
            result[name] = data
    return manifest, result


def open_archive(archive, identity, callback):
    archive = Path(archive)
    identity = Path(identity)
    require_regular(archive) if archive.stat().st_size <= MAX_FILE else None
    if not archive.is_file() or archive.is_symlink():
        raise BackupError("Missing or unsafe archive")
    require_regular(identity)
    executable("age")
    with tempfile.TemporaryDirectory(prefix="controller-restore-", dir="/run") as tmp:
        os.chmod(tmp, 0o700)
        plain = Path(tmp) / "decrypted.tar.gz"
        run_checked(["age", "-d", "-i", str(identity), "-o", str(plain),
                     str(archive)])
        return callback(*inspect_plain_archive(plain))


def verify(paths, archive, identity):
    def output(manifest, data):
        print("Verified encrypted backup, format " + str(manifest["format"]))
        print("Git commit: " + manifest["git_commit"])
        print("Checked files: " + str(len(data)))
    return open_archive(archive, identity, output)


def restore(paths, archive, identity, *, replace_existing=False):
    def apply(manifest, data):
        destinations = [paths.target(name) for name in FILES]
        if len(set(destinations)) != len(destinations):
            raise BackupError("Ambiguous restore targets")
        present = [str(p) for p in destinations if p.exists() or p.is_symlink()]
        if present:
            # Never overwrite existing private credentials automatically.
            raise BackupError("Restore requires a clean target. Existing: " +
                              ", ".join(present) +
                              ". Move existing data to secure storage manually.")
        staged = []
        try:
            for name in FILES:
                target = paths.target(name)
                ensure_private_dir(target.parent)
                tmp = target.parent / (".restore-" + uuid.uuid4().hex)
                fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                             FILES[name][2])
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data[name])
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(tmp, FILES[name][2])
                staged.append((tmp, target))
            created = []
            try:
                for tmp, target in staged:
                    if target.exists() or target.is_symlink():
                        raise BackupError("Restore target appeared: " + str(target))
                    os.replace(tmp, target)
                    created.append(target)
            except Exception:
                for target in created:
                    target.unlink(missing_ok=True)
                raise
        finally:
            for tmp, _ in staged:
                tmp.unlink(missing_ok=True)
        print("Restored " + str(len(data)) + " controller files")
        print("Original Git commit: " + manifest["git_commit"])
        print("Run controller repair to validate Vault and SSH access locally.")
    return open_archive(archive, identity, apply)


def require_not_initialized(paths):
    found = [str(paths.target(n)) for n in FILES
             if paths.target(n).exists() or paths.target(n).is_symlink()]
    if found:
        raise BackupError("Fresh install refused; existing files: " + ", ".join(found))


def fresh(paths, *, vault_binary, ssh_keygen="ssh-keygen"):
    require_not_initialized(paths)
    executable(vault_binary)
    executable(ssh_keygen)
    print("Fresh Production controller setup (no remote server commands).")
    domain = input("Domain suffix (example.com): ").strip()
    if not domain or any(char.isspace() for char in domain):
        raise BackupError("A valid domain suffix is required")
    secrets = {
        "vault_ansible_password": getpass.getpass("Initial SSH password: "),
        "vault_ansible_become_pass": getpass.getpass("Initial sudo password: "),
        "vault_cf_api_token": getpass.getpass("Cloudflare API token: "),
        "vault_common_api_key": getpass.getpass("Common API key: "),
        "vault_domain_suffix": domain,
        "vault_ssh_public_key_path": str(paths.home / ".ssh/ansible_ssh_key.pub"),
    }
    if not secrets["vault_cf_api_token"] or not secrets["vault_common_api_key"]:
        raise BackupError("API token fields cannot be empty")
    vault_pass = getpass.getpass("NEW Ansible Vault password: ")
    if not vault_pass or vault_pass != getpass.getpass("Confirm Vault password: "):
        raise BackupError("Vault password mismatch or empty")
    inventory_source = input(
        "Existing inventory file to import (empty to create a safe empty inventory): "
    ).strip()
    if inventory_source:
        source = Path(inventory_source)
        require_regular(source)
        inventory = source.read_bytes()
    else:
        inventory = b"[common]\n\n[pasarguard_nodes]\n\n[ssh_ubuntu]\n\n[abuse_protected]\n\n[port_forward_nodes]\n"
        print("An empty inventory will be created. Add real hosts before running site.yml.")
    # Ensure plaintext secrets reside only in /run tmpfs, not persistent disk.
    with tempfile.TemporaryDirectory(prefix="controller-fresh-", dir="/run") as tmp:
        os.chmod(tmp, 0o700)
        clear = Path(tmp) / "vault.json"
        clear.write_text(json.dumps(secrets), encoding="utf-8")
        clear.chmod(0o600)
        atomic_bytes(paths.home / ".ansible/vault_pass",
                     (vault_pass + "\n").encode(), 0o600)
        encrypted = Path(tmp) / "vault.encrypted"
        try:
            run_checked([vault_binary, "encrypt",
                         "--vault-password-file", str(paths.home / ".ansible/vault_pass"),
                         "--output", str(encrypted), str(clear)])
            atomic_bytes(paths.target("inventory/group_vars/all/vault.yml"),
                         encrypted.read_bytes(), 0o600)
            atomic_bytes(paths.target("inventory/hosts.ini"), inventory, 0o644)
            ensure_private_dir(paths.home / ".ssh")
            run_checked([ssh_keygen, "-t", "ed25519", "-a", "64", "-f",
                         str(paths.home / ".ssh/ansible_ssh_key"), "-N", ""])
            (paths.home / ".ssh/ansible_ssh_key").chmod(0o600)
            (paths.home / ".ssh/ansible_ssh_key.pub").chmod(0o644)
        except Exception:
            # Do not leave a half-created Vault or credential set.
            for name in FILES:
                paths.target(name).unlink(missing_ok=True)
            raise
    ensure_identity_rule(paths)
    print("Fresh controller credentials created. BACK THEM UP before use.")


def ensure_identity_rule(paths):
    config = paths.home / ".ssh/config"
    ensure_private_dir(config.parent)
    if config.exists():
        if config.is_symlink():
            raise BackupError("Refusing SSH config symlink")
        text = config.read_text(encoding="utf-8")
        if "IdentityFile ~/.ssh/ansible_ssh_key" in text:
            return
        print("SSH config already exists; add Host * IdentityFile manually if required.")
        return
    atomic_bytes(config, b"Host *\n  IdentityFile ~/.ssh/ansible_ssh_key\n", 0o600)


def repair(paths, *, vault_binary="ansible-vault"):
    for name in FILES:
        require_regular(paths.target(name))
    if paths.target("inventory/group_vars/all/vault.yml").read_bytes()[:15] != b"$ANSIBLE_VAULT;":
        raise BackupError("Vault file is not encrypted")
    run_checked([vault_binary, "view", "--vault-password-file",
                 str(paths.home / ".ansible/vault_pass"),
                 str(paths.target("inventory/group_vars/all/vault.yml"))])
    pub = run_checked(["ssh-keygen", "-y", "-f",
                       str(paths.home / ".ssh/ansible_ssh_key")]).decode().split()
    actual = (paths.home / ".ssh/ansible_ssh_key.pub").read_text().split()
    if pub[:2] != actual[:2]:
        raise BackupError("SSH private/public key pair does not match")
    ensure_identity_rule(paths)
    print("Controller Vault, SSH keypair and essential files verified.")
    print("Repair does not overwrite private files or contact remote hosts.")


def wizard(paths, *, vault_binary):
    print("Ansible Controller Setup")
    print("1) Fresh Install  2) Restore existing encrypted backup  3) Repair/Verify")
    choice = input("Choose [1/2/3]: ").strip()
    if choice == "1":
        fresh(paths, vault_binary=vault_binary)
    elif choice == "2":
        archive = input("Absolute path to downloaded .tar.gz.age backup: ").strip()
        identity = input("Absolute path to age private recovery key: ").strip()
        verify(paths, archive, identity)
        if input("Restore into empty production target? type RESTORE: ").strip() != "RESTORE":
            raise BackupError("Restore cancelled")
        restore(paths, archive, identity)
        repair(paths, vault_binary=vault_binary)
    elif choice == "3":
        repair(paths, vault_binary=vault_binary)
    else:
        raise BackupError("Invalid installation mode")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=str(DEFAULT_REPO))
    parser.add_argument("--home", default=str(DEFAULT_HOME))
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE))
    parser.add_argument("--config-dir", default=str(DEFAULT_CONFIG))
    parser.add_argument("--vault-binary", default="ansible-vault")
    cmd = parser.add_subparsers(dest="command", required=True)
    bk = cmd.add_parser("backup")
    bk.add_argument("--upload", action="store_true")
    v = cmd.add_parser("verify")
    v.add_argument("--archive", required=True)
    v.add_argument("--identity", required=True)
    r = cmd.add_parser("restore")
    r.add_argument("--archive", required=True)
    r.add_argument("--identity", required=True)
    cmd.add_parser("install")
    cmd.add_parser("repair")
    args = parser.parse_args()
    paths = Paths(args.repository, args.home, args.state_dir, args.config_dir)
    if os.geteuid() != 0:
        raise BackupError("Run as root on the controller")
    if args.command == "backup":
        backup(paths, upload=args.upload)
    elif args.command == "verify":
        verify(paths, args.archive, args.identity)
    elif args.command == "restore":
        restore(paths, args.archive, args.identity)
    elif args.command == "install":
        wizard(paths, vault_binary=args.vault_binary)
    elif args.command == "repair":
        repair(paths, vault_binary=args.vault_binary)


if __name__ == "__main__":
    try:
        main()
    except (BackupError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        # Avoid echoing exception strings from third-party APIs, CLI commands
        # or secret-bearing requests.
        if isinstance(exc, BackupError):
            print("ERROR: " + str(exc), file=sys.stderr)
        else:
            print("ERROR: Controller operation failed (details suppressed)", file=sys.stderr)
        sys.exit(1)
