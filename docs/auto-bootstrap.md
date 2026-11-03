# Auto Bootstrap for every inventory host (no manual group)

## Objective

Add new servers to their **normal functional groups** in the private
`inventory/hosts.ini` exactly once. Do not create or move hosts between a
temporary bootstrap group and their final group.

This workflow has two one-time/recurring commands:

1. On the existing managed fleet **once**, after confirming those hosts really
   completed Bootstrap, adopt their state by writing a completion marker.
2. For every future batch, add new hosts to `hosts.ini` and run a single
   auto-bootstrap command. Existing marked hosts are skipped.

The persistent state file is `/var/lib/ansible-bootstrap-complete`, with the
exact content `completed` plus newline, owned by root and mode 0644.

## Commands

Preview one-time marker adoption without changing hosts:

```bash
ansible-playbook playbooks/operations/bootstrap-adopt-existing.yml \
  -e bootstrap_adopt_dry_run=true
```

After confirming the existing hosts are actually managed, adopt them once:

```bash
ansible-playbook playbooks/operations/bootstrap-adopt-existing.yml
```

Preview the entire inventory **without making changes**:

```bash
ansible-playbook playbooks/bootstrap-auto.yml \
  -e bootstrap_auto_discover_only=true
```

Bootstrap only positively identified new hosts:

```bash
ansible-playbook playbooks/bootstrap-auto.yml
```

For a one/two-server canary, add `--limit HOST1,HOST2` to either command.
Do not change the Inventory groups for this purpose.

Manual Bootstrap remains available with
`ansible-playbook playbooks/bootstrap.yml -e bootstrap_host=HOST`.

## How discovery works

Every host is checked using read-only POSIX commands via SSH, with no
Python dependency. A key-only probe runs first; for hosts not already clearly
managed, a password-only probe uses the existing Vault initial SSH password.
SSH multiplexing is disabled for the probes so a key connection cannot be
mistaken for a successful password login. For a key-only NEW host, a third
read-only probe checks whether the public key configured by
`vault_ssh_public_key_path` is already present in the SSH account's
`~/.ssh/authorized_keys`. If it matches, Bootstrap runs using the working
SSH Key and does not supply the initial Vault login password.
This reduces the risk that exclusive authorized-key configuration replaces
a working key with an unrelated one. Operators must still independently
verify the server host fingerprint and that the matching private key is
available to the Ansible controller. Without a key match, the host stays
unmodified for review.
Passwords and probe output are suppressed in Ansible logs; only the final
classification is displayed.

| Result | Action |
| --- | --- |
| Valid marker and key-based SSH | Skip as `managed` |
| Valid marker, but key failed and password worked | Skip and report `managed_key_unavailable` |
| Marker absent but current Ansible hardening config present | Skip as `needs_adoption` |
| Hardening present but unexpected | Skip and report `review_hardening` |
| Marker incomplete, invalid, or a symlink | Skip and report `invalid_marker` |
| No marker and no hardening; **initial password login works** | Bootstrap as `candidate` |
| Key works, no marker/hardening, password fails, and official Ansible public key is already authorized | Bootstrap as `candidate_key` over SSH Key |
| Key works, no marker/hardening, password fails, but official Ansible public key cannot be confirmed | Skip as `key_only_unmanaged` for review |
| Neither probe works | Skip as `unreachable` |

The one-time adoption playbook connects only via SSH **public key** and
writes a marker only when the current Ansible SSH hardening file has
`PasswordAuthentication no` and `PubkeyAuthentication yes`. It never
attempts password login, reboots, runs Bootstrap or changes network settings.
The existence of hardening alone does not prove all historical DNS/update
steps completed: the operator must confirm that before adopting existing hosts.

Internal Ansible runtime groups are used only to pass verified candidates
to the shared Bootstrap playbook. Nothing writes to or modifies `hosts.ini`.
Bootstrap processes targets sequentially (`serial: 1`). Automatic mode skips
the old manual Bootstrap behavior that globally emptied the controller
`known_hosts`; manual Bootstrap still preserves that historical behavior.
The controller currently has `host_key_checking=False`, which weakens SSH
identity assurance. Verify server fingerprints out of band, especially when
replacing an IP. This feature does **not** fix that security issue.

## Failure handling

Bootstrap creates the marker **only after** SSH hardening, DNS, controller
shortcuts, handler flush, SSH reconnection, system update and any required
reboot complete successfully. It does not mean `site.yml` has been run.

If Bootstrap stops mid-operation, the marker stays absent. If hardening was
installed, the next auto-run reports `needs_adoption` rather than retrying a
partially configured machine. Investigate the cause, then recover explicitly
using the manual procedure. Invalid marker files are never overwritten by
discovery or automatic adoption.

After processing eligible new hosts, unresolved inventory states cause
a non-success summary to avoid falsely claiming the fleet is fully onboarded.
Use preview first and a new disposable canary before a large rollout.

## Coverage

GitHub Actions tests the probe against temporary local fixtures for new,
marked, unmarked/hardened, partially marked, unexpected-hardening and symlink
states. Contract tests enforce the key-first/password-second flow, secret
suppression, marker-last policy, serial execution, adoption restrictions
and in-memory candidate targeting. No CI job uses real inventory, passwords
or production servers.

Actual new-server password or key login, SSH cutover and reboot require
controlled operator tests after merging to `development`. A read-only
canary using `--limit OneProvider-IT -e bootstrap_auto_discover_only=true`
should first show `candidate_key`. Do not perform a changing run until the
server host fingerprint and configured Ansible public/private key pair have
been verified out of band.
