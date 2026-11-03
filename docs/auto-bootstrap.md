# Auto Bootstrap for every inventory host (no manual group)

## Objective

Add new servers to their **normal functional groups** in the private
`inventory/hosts.ini` exactly once. Do not create or move hosts between a
temporary bootstrap group and their final group.

The existing fleet completed its one-time Marker migration; that migration
Playbook has been retired. For each new batch, add fresh hosts to `hosts.ini`
and run Auto Bootstrap. Existing marked hosts are skipped.

The persistent state file is `/var/lib/ansible-bootstrap-complete`, with the
exact content `completed` plus newline, owned by root and mode 0644.

## Commands

The retired one-time adoption utility is not part of future onboarding.
Do not bulk-mark incomplete or unverified hosts.

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
mistaken for a successful password login. **When the key-only probe succeeds,
the initial-password probe is skipped entirely**; password fallback is
attempted only when key-based access cannot be established. This avoids
a misleading `UNREACHABLE` authentication error for newly provisioned
SSH-key hosts (for example OneProvider). For a key-only NEW host, a third
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
| Key works, no marker/hardening, and the official Ansible public key is already authorized | Bootstrap as `candidate_key` over SSH Key (no password probe) |
| Key works, no marker/hardening, but official Ansible public key cannot be confirmed | Skip as `key_only_unmanaged` for review |
| Neither probe works | Skip as `unreachable` |

The existence of SSH hardening alone does not prove the full Bootstrap
completed. A host with this state is reported as `needs_adoption` and must
be reviewed and recovered manually. The former bulk-adoption command was
retired after the previous fleet migration.

Internal Ansible runtime groups are used only to pass verified candidates
to the shared Bootstrap playbook. When none exist, the imported Bootstrap
uses the intentionally empty `all:!all` host intersection instead of a missing
runtime group. This prevents the noisy `__bootstrap_auto_pending` pattern
warning without disabling warnings for genuine misspelled inventory hosts.
Nothing writes to or modifies `hosts.ini`.
Automatic discovery uses the same no-`serial` model as `site.yml`.
All verified new hosts run in a **single Ansible batch**, with no fixed
5-, 10-, or other host-count limit. Package upgrades and reboot operations
can therefore progress on multiple new servers instead of finishing one
entire host before starting another. The normal Ansible `forks` worker
setting still controls how many host tasks execute at the exact same instant;
we do not modify its global value. To use more workers on a large rollout,
an operator may choose `-f 20` or another count explicitly.

Manual `bootstrap.yml` remains sequential by default. The
`controller_ssh_config` role is already delegated to localhost with
`run_once`, so the shared controller SSH config is generated just once
for the single automatic Bootstrap batch. Cloudflare DNS records are
per-host (`inventory_hostname`), allowing distinct records to be updated
concurrently. Any host that fails before the final step remains unmarked;
other eligible hosts may finish. Automatic mode skips
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
discovery or automatic Bootstrap.

After processing eligible new hosts, unresolved inventory states cause
a non-success summary to avoid falsely claiming the fleet is fully onboarded.
Use preview first and a new disposable canary before a large rollout.

## Coverage

GitHub Actions tests the probe against temporary local fixtures for new,
marked, unmarked/hardened, partially marked, unexpected-hardening and symlink
states. Contract tests enforce the key-first/password-second flow, secret
suppression, marker-last policy and in-memory candidate targeting. Release contracts also verify that automatic
discovery has no serial batch cap, that automatic Bootstrap uses one 100%
batch, manual Bootstrap retains serial 1, controller config is a singleton
write, and Cloudflare records remain per-host. No CI job uses real inventory, passwords
or production servers.

Actual new-server password or key login, SSH cutover and reboot require
controlled operator tests. Before changing a fresh canary, use
`--limit NEW_HOST -e bootstrap_auto_discover_only=true` and verify the
server host fingerprint and Ansible public/private key pair out of band.
The preview should report `candidate` or `candidate_key` only when the
corresponding authentication gate succeeds.
