#!/usr/bin/env python3
"""Read-only BIOS GRUB debconf preflight for system_update.

Never runs grub-install or writes to a disk. Report the planned debconf
selection as JSON; Ansible makes the controlled change only when needed.
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

BIOS_BOOT_GUID = "21686148-6449-6e6f-744e-656564454649"


def run(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        args, input=input_text, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def decision(
    *, uefi: bool, grub_pc_installed: bool, current: str = "",
    empty: bool = False, valid_current: bool = False,
    candidate: str = "", disk_count: int = 0,
    partition_table: str = "", bios_boot_partition: bool = False,
) -> dict[str, str]:
    """Pure policy: no guessing in ambiguous boot configurations."""
    if uefi:
        return {"action": "skip", "reason": "UEFI host: grub-pc BIOS settings untouched"}
    if not grub_pc_installed:
        return {"action": "skip", "reason": "grub-pc is not installed"}
    if valid_current and not empty:
        return {"action": "keep", "reason": "existing whole-disk GRUB target is valid"}
    if valid_current and empty:
        return {"action": "preseed", "device": current, "reason": "clear stale skip-install answer"}
    if not candidate:
        return {"action": "block", "reason": "cannot resolve /boot to one physical disk"}
    if disk_count != 1:
        return {"action": "block", "reason": "multiple or no disks: firmware boot disk ambiguous"}
    if partition_table not in ("gpt", "dos"):
        return {"action": "block", "reason": "unknown partition table; refusing to select boot disk"}
    if partition_table == "gpt" and not bios_boot_partition:
        return {"action": "block", "reason": "BIOS/GPT disk lacks a BIOS Boot partition"}
    return {"action": "preseed", "device": candidate,
            "reason": "replace missing or stale GRUB install target"}


def is_whole_disk(device: str) -> bool:
    if not device.startswith("/dev/") or not Path(device).exists():
        return False
    try:
        if not stat.S_ISBLK(os.stat(device).st_mode):
            return False
        return run("lsblk", "-dn", "-o", "TYPE", "--", device) == "disk"
    except (OSError, subprocess.CalledProcessError):
        return False


def read_debconf(question: str) -> str:
    response = run(
        "debconf-communicate", "grub-pc",
        input_text=f"GET {question}\n",
    )
    line = response.splitlines()[-1] if response else ""
    if not line.startswith("0"):
        raise ValueError(f"debconf GET {question} failed: {line}")
    return line[2:] if line.startswith("0 ") else ""


def preferred_device_id(disk: str) -> str:
    """Prefer stable disk by-id; never use per-partition aliases."""
    directory = Path("/dev/disk/by-id")
    if not directory.is_dir():
        return disk
    matches = []
    for path in directory.iterdir():
        if re.search(r"-part[0-9]+$", path.name):
            continue
        if path.is_symlink() and os.path.realpath(path) == disk:
            matches.append(path)
    def priority(path: Path) -> tuple[int, str]:
        prefixes = ("wwn-", "nvme-eui.", "scsi-", "virtio-", "ata-")
        return (next((i for i, p in enumerate(prefixes)
                      if path.name.startswith(p)), len(prefixes)), path.name)
    selected = str(min(matches, key=priority)) if matches else disk
    if not re.fullmatch(r"/dev/[A-Za-z0-9_./:+-]+", selected):
        raise ValueError("GRUB target contains unsupported characters")
    return selected


def discover_candidate() -> dict[str, object]:
    boot_device = run("grub-probe", "--target=device", "/boot")
    parents = run("lsblk", "-n", "-o", "PKNAME", "--", boot_device).splitlines()
    if len(parents) != 1 or not parents[0].strip():
        return {}
    disk = "/dev/" + parents[0].strip()
    if not is_whole_disk(disk):
        return {}
    disks = [
        line for line in run("lsblk", "-dn", "-o", "TYPE").splitlines()
        if line.strip() == "disk"
    ]
    pttype = run("lsblk", "-dn", "-o", "PTTYPE", "--", disk).strip().lower()
    parttypes = run("lsblk", "-n", "-o", "PARTTYPE", "--", disk).lower()
    return {
        "candidate": preferred_device_id(disk),
        "disk_count": len(disks),
        "partition_table": pttype,
        "bios_boot_partition": BIOS_BOOT_GUID in parttypes,
    }


def main() -> int:
    try:
        uefi = Path("/sys/firmware/efi").is_dir()
        if uefi:
            result = decision(uefi=True, grub_pc_installed=False)
        else:
            try:
                installed = run(
                    "dpkg-query", "-W", "-f=${Status}", "grub-pc"
                ) == "install ok installed"
            except subprocess.CalledProcessError:
                installed = False
            if not installed:
                result = decision(uefi=False, grub_pc_installed=False)
            else:
                current = read_debconf("grub-pc/install_devices")
                empty_value = read_debconf("grub-pc/install_devices_empty")
                if empty_value not in ("", "true", "false"):
                    raise ValueError("unexpected GRUB skip-install debconf value")
                selected = [s.strip() for s in current.split(",") if s.strip()]
                valid = bool(selected) and all(is_whole_disk(s) for s in selected)
                if valid:
                    # Preserve a valid multi-device selection verbatim.
                    result = decision(
                        uefi=False, grub_pc_installed=True,
                        current=current, empty=empty_value == "true",
                        valid_current=True,
                    )
                else:
                    result = decision(
                        uefi=False, grub_pc_installed=True,
                        current=current, empty=empty_value == "true",
                        **discover_candidate(),
                    )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        result = {"action": "block", "reason": f"GRUB preflight error: {exc}"}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
