#!/usr/bin/env python3
"""Isolated unit contracts for BIOS GRUB preflight; never touches real boot disks."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import pathlib
import unittest
from unittest import mock

SOURCE = pathlib.Path(__file__).resolve().parents[2] / "roles/system_update/files/grub_preflight.py"
SPEC = importlib.util.spec_from_file_location("grub_preflight", SOURCE)
assert SPEC is not None and SPEC.loader is not None
grub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grub)


class GrubPreflightPolicyTests(unittest.TestCase):
    def test_uefi_is_untouched_even_if_grub_pc_is_installed(self):
        result = grub.decision(uefi=True, grub_pc_installed=True)
        self.assertEqual(result["action"], "skip")

    def test_hosts_without_grub_pc_are_skipped(self):
        result = grub.decision(uefi=False, grub_pc_installed=False)
        self.assertEqual(result["action"], "skip")

    def test_valid_existing_device_is_untouched(self):
        result = grub.decision(
            uefi=False, grub_pc_installed=True, current="/dev/sda",
            valid_current=True, empty=False,
        )
        self.assertEqual(result["action"], "keep")

    def test_valid_existing_device_with_skip_answer_is_corrected(self):
        result = grub.decision(
            uefi=False, grub_pc_installed=True, current="/dev/sda",
            valid_current=True, empty=True,
        )
        self.assertEqual(result["action"], "preseed")
        self.assertEqual(result["device"], "/dev/sda")

    def test_stale_virtio_device_is_replaced_only_with_unambiguous_disk(self):
        result = grub.decision(
            uefi=False, grub_pc_installed=True, current="/dev/vda",
            candidate="/dev/disk/by-id/scsi-ci-test", disk_count=1,
            partition_table="gpt", bios_boot_partition=True,
        )
        self.assertEqual(result["action"], "preseed")
        self.assertEqual(result["device"], "/dev/disk/by-id/scsi-ci-test")

    def test_bios_gpt_without_bios_boot_partition_blocks(self):
        result = grub.decision(
            uefi=False, grub_pc_installed=True, candidate="/dev/sda",
            disk_count=1, partition_table="gpt", bios_boot_partition=False,
        )
        self.assertEqual(result["action"], "block")

    def test_multiple_disks_block_when_old_target_is_invalid(self):
        result = grub.decision(
            uefi=False, grub_pc_installed=True, candidate="/dev/sda",
            disk_count=2, partition_table="gpt", bios_boot_partition=True,
        )
        self.assertEqual(result["action"], "block")

    def test_missing_boot_parent_blocks(self):
        result = grub.decision(uefi=False, grub_pc_installed=True, disk_count=1)
        self.assertEqual(result["action"], "block")

    def test_unrecognized_partition_table_blocks(self):
        result = grub.decision(
            uefi=False, grub_pc_installed=True, candidate="/dev/sda",
            disk_count=1, partition_table="unknown",
        )
        self.assertEqual(result["action"], "block")

    def test_single_mbr_disk_can_be_selected_without_bios_boot_partition(self):
        result = grub.decision(
            uefi=False, grub_pc_installed=True, candidate="/dev/sda",
            disk_count=1, partition_table="dos",
        )
        self.assertEqual(result["action"], "preseed")

    def test_runtime_reads_debconf_without_writing_to_disk(self):
        fake_path = mock.Mock()
        fake_path.is_dir.return_value = False
        with (
            mock.patch.object(grub, "Path", return_value=fake_path),
            mock.patch.object(grub, "run", return_value="install ok installed"),
            mock.patch.object(grub, "read_debconf", side_effect=["/dev/vda", "true"]),
            mock.patch.object(grub, "is_whole_disk", return_value=False),
            mock.patch.object(grub, "discover_candidate", return_value={
                "candidate": "/dev/sda",
                "disk_count": 1,
                "partition_table": "gpt",
                "bios_boot_partition": True,
            }),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(grub.main(), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["action"], "preseed")
        self.assertEqual(result["device"], "/dev/sda")

    def test_grub_absent_is_not_a_fatal_error(self):
        fake_path = mock.Mock()
        fake_path.is_dir.return_value = False
        with (
            mock.patch.object(grub, "Path", return_value=fake_path),
            mock.patch.object(
                grub, "run", side_effect=grub.subprocess.CalledProcessError(1, "dpkg-query")
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(grub.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["action"], "skip")


if __name__ == "__main__":
    unittest.main()
