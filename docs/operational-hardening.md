# Operational hardening: CI contracts and remaining failure tests

This document records the first three hardening workstreams. It does **not**
authorize production playbook execution or claim successful real fault injection.

## Documentation drift / SSH trust

- Bootstrap's controller-only first play clears **every** entry in the selected
  controller user's `known_hosts`, including unrelated hosts, before remote SSH.
- Remote Bootstrap roles: `ssh_security`, `cloudflare_dns`,
  `controller_ssh_config`. It then flushes SSH handlers, resets the connection,
  requires successful `wait_for_connection`, and only **then** executes
  `system_update` (optional reboot when required).
- `ansible.cfg` currently disables `host_key_checking`. The global wipe and
  disabled verification weaken host identity assurance. Restore host-key trust
  through a separate reviewed migration, not a silent change to Bootstrap.
- `speedtest_cli` and `floatip_manager` belong in `site.yml`, not Bootstrap.

`tests/release/repository_contracts.py` and
`tests/release/test_operational_hardening.py` enforce the relevant playbook,
role, controller-file and documentation contracts.

## Secret scanning and supply-chain trust

- CI runs the Gitleaks v3.0.0 GitHub Action pinned to a full commit SHA with a
  full-history checkout. `Secret Scan` is mandatory in `CI Gate`.
- The action requires no production Vault, SSH or provider credentials. For
  this personal-account repository it does not require a paid organization
  license. PR comments and scan artifact uploads are disabled.
- Secret scanning is defense in depth: scanners can miss secrets or produce
  false positives. If a real secret is found, rotate/revoke it; deleting it
  from the newest commit does not remove its history.

**Unresolved integrity limitation:** Neither currently published stable upstream
GitHub Release (`floatip-manager` or `iptables-forward-manager`) contains
checksum/signature assets. Ansible currently validates stable semver release
metadata, uses HTTPS downloads, and checks installed script syntax; these are
not independent signed/checksum verification. Do not invent a SHA value or
silently lock to a moving source. A future security change should have upstream
publish an authenticated artifact manifest/signature, define trusted key
distribution, verify downloads *before* replacing live files, and cover
tampered/missing manifest cases in isolated tests.

## Failure contracts covered in offline CI

- APT tasks in the system-update and unattended-security-tool installation
  paths wait up to 300 seconds for a package manager lock rather than
  immediately failing or deleting lock files. The lock wait is bounded; after
  expiration normal Ansible failure stops the operation.
- A synthetic *bad* APT task with `lock_timeout` removed must fail the policy
  test (negative-case assertion).
- Bootstrap SSH reconnect is mandatory and bounded before any final OS upgrade.
- System-update reboot occurs only when requested **and** required; reboot and
  connection timeouts must remain configurable and positive.
- GitHub release metadata handling is fail-closed for non-404 errors. FloatIP
  fallback is allowed only for no stable Release (HTTP 404); Port Forward
  Manager requires HTTP 200 and stable semver metadata.
- The pinned Gitleaks action must remain a mandatory CI Gate dependency.

The tests do not SSH to production, install OS packages, reboot a machine,
kill APT, or contact provider APIs. Run them in the repository CI:

```bash
python3 -m unittest discover -s tests/release -p 'test_operational_hardening.py' -v
```

`scripts/validate.sh` executes them for PRs to `development`; Full Release
Qualification executes them again for protected promotions to `main`.

## Sequential security-update rollout with unreachable hosts

`playbooks/operations/security-updates.yml` first checks reachability
without `serial` and without gathering facts, marking eligible hosts in a
temporary in-memory group. It then runs the original `security_updates` role
**one full host at a time** (`serial: 1`), rechecking the connection immediately
before starting a host and ending only that host if it becomes unavailable.

If a host is already offline, or goes offline while earlier hosts are being
processed, that host is skipped and the rollout continues to remaining
reachable hosts. After all reachable hosts are attempted, the final summary
lists unavailable hosts and returns a nonzero result so the operator can retry
the ordinary command after restoring connectivity. No inventory, credentials
or SSH host configuration are changed by discovery.

This specifically handles host unavailability **before** entering a host's
update tasks. A sudden connection loss or an actual APT/module failure
*during* a host's role remains a normal failure; it is not swallowed or
automatically retried. Production validation of such later interruptions
requires a separate staging test.

Standard command (no new parameters):

```bash
ansible-playbook playbooks/operations/security-updates.yml
```

The offline CI regression invokes real Ansible against two local fixture
hosts with an intentionally refused loopback connection between them. The
update role is substituted by harmless debug output; CI checks that the
last host was reached and that the final status reports the unavailable
host. It never connects to production.

## Deferred real failure tests (operator-controlled staging only)

1. Hold a legitimate APT/dpkg lock in an expendable test VM, verify the bounded
   wait and clean failure on expiry, then verify a successful normal rerun.
2. Disconnect SSH between hardening and the rebooting update on an expendable
   VM; verify the upgrade is not invoked until connection succeeds.
3. Test interrupted reboot, host availability timeout, and manual recovery on
   a provider console with a snapshot.
4. Serve corrupt/altered release artifacts and malformed GitHub metadata from
   local fixtures, then validate no state is changed; independent cryptographic
   verification remains blocked on upstream signed/checksum manifests.
5. Review host-key pinning and fingerprint verification before any migration
   away from the current global `known_hosts` reset.

Do not run these failure-injection scenarios on working production forwarding,
PasarGuard, or Floating IP hosts without a separately approved rollback plan.
