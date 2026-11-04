# AGENTS.md

## Purpose

This repository manages production-oriented Ansible infrastructure.

Agents working in this repository must prioritize safety, clarity,
maintainability, reviewability, and preservation of production behavior unless a
change is explicitly requested.

## Engineering Principles

- SRP: each Ansible role must have one clear responsibility.
- SOLID: prefer small, composable, well-scoped units.
- KISS: avoid unnecessary abstraction and complexity.
- DRY: shared behavior must be implemented once and reused.
- Idempotency: converged tasks should report `ok` when no state change is required.
- Explicit orchestration: playbooks coordinate roles; role logic belongs in roles.
- Preserve existing behavior unless a change is explicitly requested.
- Prefer small, reviewable commits over large unrelated refactors.
- Avoid unrelated cleanup in the same commit.

## Production Safety Rules

These rules are mandatory:

- Never SSH to production infrastructure hosts.
- Never execute Ansible against production hosts.
- Never use or request production passwords, API keys, Vault secrets, private keys, or tokens.
- Never read ignored production inventory or Vault files.
- Never modify production inventory, Vault data, or credentials.
- Never modify Git remotes or configure Git credentials.
- Never force-push.
- Never merge pull requests.
- Never delete `main` or `development`.
- Never rewrite published/shared history.
- Stop on an unexpected failure and report it.

Production deployment and production validation are performed manually by the operator. Repository validation is enforced by GitHub Actions.

## Branch and Git Workflow

The current branch model is:

```text
feature/* or fix/*
        ↓ PR
development
        ↓ later promotion PR
main
```

Rules:

- Create repository changes from `development` on a feature/fix branch.
- Do not commit or push directly to `development` or `main`.
- Feature-branch commits/pushes and opening a PR to `development` are allowed only when the task explicitly requests repository changes.
- The operator reviews and merges PRs.
- Do not merge, force-push, delete protected branches, or rebase shared branches.
- Keep commits focused and use clear commit messages.
- Before committing, inspect the intended diff and confirm no secrets or production-only files are included.

## Ansible Design Rules

- Every role should have one clear responsibility.
- Do not create generic catch-all roles when responsibilities can be named explicitly.
- Keep operational playbooks separate from ordinary desired-state orchestration unless explicitly requested otherwise.
- Reuse the same role from multiple playbooks instead of duplicating tasks.
- Preserve existing host targeting and group behavior unless the task explicitly changes it.
- Prefer built-in Ansible modules over `shell` or `command` when practical.
- Preserve check-mode behavior where the role supports it.
- Use `delegate_to`, `run_once`, handlers, tags, and variables intentionally.
- Avoid hidden side effects.
- Do not silently change reboot behavior, SSH access, firewall policy, package upgrades, DNS behavior, addressing, or monitoring behavior.

## Current Behavioral Contracts

- `bootstrap.yml` is the initial onboarding workflow.
  - **Manual** Bootstrap clears all controller-user `known_hosts` entries in its first play, including unrelated hosts. **Automatic** Bootstrap skips this global reset. The current SSH identity risk remains; verify host fingerprints independently.
  - Its remote roles run in order: `ssh_security`, `cloudflare_dns`, `controller_ssh_config`.
  - Remote tasks flush SSH handlers, reset the connection, verify bounded SSH reconnection and run `system_update` with reboot-on-required enabled. The completion Marker is written **only after** the OS update and any required reboot succeed.
  - `speedtest_cli` and `floatip_manager` are intentionally omitted from Bootstrap and are installed only by `site.yml`.
  - `ansible.cfg` currently sets `host_key_checking = False`. This is a security risk; do not enable host-key checking or change the global wipe behavior without a separately reviewed SSH trust/bootstrap migration.
- `bootstrap-auto.yml` inspects all inventory hosts without changing inventory groups on disk. Only hosts without a valid Marker or managed hardening **and** with confirmed initial-password SSH access, or key-only SSH access whose configured official Ansible public key is already authorized, may be automatically bootstrapped together in a single unrestricted Ansible
  batch. Manual `bootstrap.yml` remains sequential by default. Do not add
  fixed-size `serial` limits to automatic discovery or Bootstrap. Unreachable, ambiguous or partially managed hosts must be skipped and explicitly reported.
  - The `quiet_bootstrap_auth` stdout callback only replaces expected
    unreachable output for the three `no_log` and `ignore_unreachable`
    discovery probes. Keep all actual Bootstrap failures and the final
    fail-closed classification visible. Preserve the PasarGuard PEM callback.
- The completed one-time fleet Marker adoption workflow was retired; do not
  reintroduce bulk marker writing. Never infer successful Bootstrap from a
  missing Marker or from a hardening file alone.
- `site.yml` is the main desired-state workflow.
  - The all-host play includes SSH/controller config, Cloudflare DNS, hostname, resolver, base packages, Speedtest CLI, FloatIP manager, and monitoring.
  - PasarGuard-specific roles remain scoped to `pasarguard_nodes`.
  - The native `port_forward_manager` role is limited to `port_forward_nodes`; it installs the tool and units without activating or modifying live forwarding or legacy state.
- `floatip_manager` installs only on hosts detected as Hetzner and must not change floating addresses merely by being installed.
- `optimization` runs only through `playbooks/operations/optimize.yml`; it is not part of `site.yml`.
  - The default host pattern is `common`.
  - `optimize_hosts` can explicitly override that pattern.
  - The repository-owned native role must keep its pre/post network and Docker safety assertions.
  - Normal converged runs are expected to be idempotent and `--check --diff` must remain non-mutating.
- `security-updates.yml`, `system-update.yml`, `ping-control.yml`,
  `optimize.yml`, and `show-pasarguard-certificate.yml` remain
  independent operational playbooks. Standalone `security.yml` and
  `port-forward-manager.yml` were retired; their roles still run in `site.yml`.
  - The two maintenance update playbooks target `all` with `serial: 1`; their APT tasks must use a bounded `lock_timeout` and must not kill package-manager processes or delete lock files.
  - `system_update` is Debian-family only; unsupported families must fail
    without making package changes.
- `security_updates` keeps unattended security installation enabled while automatic reboot remains disabled by default.
  - `needrestart` may restart ordinary services automatically, but critical network-manager services are excluded by default and deferred to controlled maintenance.
- The PasarGuard installer command includes a credential and must retain
  `no_log: true`. Only its credential-bearing task is censored; ordinary
  diagnostics remain visible. Never copy node certificates to the controller.
  Use the read-only `show-pasarguard-certificate.yml` operation to display
  public X.509 PEM, validity dates and fingerprint from the remote source;
  never expose a private key or imply that the operation renews certificates.
  The PEM must render as separate, copy-ready terminal lines (not JSON-escaped
  \n) via the isolated public-certificate aggregate callback. All other
  playbook logs stay unchanged; no private keys or controller copies.

## Purpose

This repository manages production-oriented Ansible infrastructure.

Agents working in this repository must prioritize safety, clarity,
maintainability, reviewability, and preservation of production behavior unless a
change is explicitly requested.

## Engineering Principles

- SRP: each Ansible role must have one clear responsibility.
- SOLID: prefer small, composable, well-scoped units.
- KISS: avoid unnecessary abstraction and complexity.
- DRY: shared behavior must be implemented once and reused.
- Idempotency: converged tasks should report `ok` when no state change is required.
- Explicit orchestration: playbooks coordinate roles; role logic belongs in roles.
- Preserve existing behavior unless a change is explicitly requested.
- Prefer small, reviewable commits over large unrelated refactors.
- Avoid unrelated cleanup in the same commit.

## Production Safety Rules

These rules are mandatory:

- Never SSH to production infrastructure hosts.
- Never execute Ansible against production hosts.
- Never use or request production passwords, API keys, Vault secrets, private keys, or tokens.
- Never read ignored production inventory or Vault files.
- Never modify production inventory, Vault data, or credentials.
- Never modify Git remotes or configure Git credentials.
- Never force-push.
- Never merge pull requests.
- Never delete `main` or `development`.
- Never rewrite published/shared history.
- Stop on an unexpected failure and report it.

Production deployment and production validation are performed manually by the operator. Repository validation is enforced by GitHub Actions.

## Branch and Git Workflow

The current branch model is:

```text
feature/* or fix/*
        ↓ PR
development
        ↓ later promotion PR
main
```

Rules:

- Create repository changes from `development` on a feature/fix branch.
- Do not commit or push directly to `development` or `main`.
- Feature-branch commits/pushes and opening a PR to `development` are allowed only when the task explicitly requests repository changes.
- The operator reviews and merges PRs.
- Do not merge, force-push, delete protected branches, or rebase shared branches.
- Keep commits focused and use clear commit messages.
- Before committing, inspect the intended diff and confirm no secrets or production-only files are included.

## Ansible Design Rules

- Every role should have one clear responsibility.
- Do not create generic catch-all roles when responsibilities can be named explicitly.
- Keep operational playbooks separate from ordinary desired-state orchestration unless explicitly requested otherwise.
- Reuse the same role from multiple playbooks instead of duplicating tasks.
- Preserve existing host targeting and group behavior unless the task explicitly changes it.
- Prefer built-in Ansible modules over `shell` or `command` when practical.
- Preserve check-mode behavior where the role supports it.
- Use `delegate_to`, `run_once`, handlers, tags, and variables intentionally.
- Avoid hidden side effects.
- Do not silently change reboot behavior, SSH access, firewall policy, package upgrades, DNS behavior, addressing, or monitoring behavior.

## Current Behavioral Contracts

- `bootstrap.yml` is the initial onboarding workflow.
  - **Manual** Bootstrap clears all controller-user `known_hosts` entries in its first play, including unrelated hosts. **Automatic** Bootstrap skips this global reset. The current SSH identity risk remains; verify host fingerprints independently.
  - Its remote roles run in order: `ssh_security`, `cloudflare_dns`, `controller_ssh_config`.
  - Remote tasks flush SSH handlers, reset the connection, verify bounded SSH reconnection and run `system_update` with reboot-on-required enabled. The completion Marker is written **only after** the OS update and any required reboot succeed.
  - `speedtest_cli` and `floatip_manager` are intentionally omitted from Bootstrap and are installed only by `site.yml`.
  - `ansible.cfg` currently sets `host_key_checking = False`. This is a security risk; do not enable host-key checking or change the global wipe behavior without a separately reviewed SSH trust/bootstrap migration.
- `bootstrap-auto.yml` inspects all inventory hosts without changing inventory groups on disk. Only hosts without a valid Marker or managed hardening **and** with confirmed initial-password SSH access, or key-only SSH access whose configured official Ansible public key is already authorized, may be automatically bootstrapped together in a single unrestricted Ansible
  batch. Manual `bootstrap.yml` remains sequential by default. Do not add
  fixed-size `serial` limits to automatic discovery or Bootstrap. Unreachable, ambiguous or partially managed hosts must be skipped and explicitly reported.
- The completed one-time fleet Marker adoption workflow was retired; do not
  reintroduce bulk marker writing. Never infer successful Bootstrap from a
  missing Marker or from a hardening file alone.
- `site.yml` is the main desired-state workflow.
  - The all-host play includes SSH/controller config, Cloudflare DNS, hostname, resolver, base packages, Speedtest CLI, FloatIP manager, and monitoring.
  - PasarGuard-specific roles remain scoped to `pasarguard_nodes`.
  - The native `port_forward_manager` role is limited to `port_forward_nodes`; it installs the tool and units without activating or modifying live forwarding or legacy state.
- `floatip_manager` installs only on hosts detected as Hetzner and must not change floating addresses merely by being installed.
- `optimization` runs only through `playbooks/operations/optimize.yml`; it is not part of `site.yml`.
  - The default host pattern is `common`.
  - `optimize_hosts` can explicitly override that pattern.
  - The repository-owned native role must keep its pre/post network and Docker safety assertions.
  - Normal converged runs are expected to be idempotent and `--check --diff` must remain non-mutating.
- `security-updates.yml`, `system-update.yml`, `ping-control.yml`,
  `optimize.yml`, and `show-pasarguard-certificate.yml` remain
  independent operational playbooks. Standalone `security.yml` and
  `port-forward-manager.yml` were retired; their roles still run in `site.yml`.
  - The two maintenance update playbooks target `all` with `serial: 1`; their APT tasks must use a bounded `lock_timeout` and must not kill package-manager processes or delete lock files.
  - `system_update` is Debian-family only; unsupported families must fail
    without making package changes.
- `security_updates` keeps unattended security installation enabled while automatic reboot remains disabled by default.
  - `needrestart` may restart ordinary services automatically, but critical network-manager services are excluded by default and deferred to controlled maintenance.
- The PasarGuard installer command includes a credential and must retain
  `no_log: true`. Only its credential-bearing task is censored; ordinary
  diagnostics remain visible. Never copy node certificates to the controller.
  Use the read-only `show-pasarguard-certificate.yml` operation to display
  public X.509 PEM, validity dates and fingerprint from the remote source;
  never expose a private key or imply that the operation renews certificates.
  The PEM must render as separate, copy-ready terminal lines (not JSON-escaped
  `\\n`); keep the certificate-view operation read-only and multi-host-safe.
- The `abuse_firewall_script_path` default is the sole source for the
  deployed script path, scheduled cron job, and initial-update handler.
- Monitoring target generation remains inventory-driven.
- Public repository files remain sanitized.
- Real inventory, real Vault files, Vault passwords, and private keys remain excluded from Git.

## SSH Key Contract

- `ssh_security` reads the controller-side public-key path from `vault_ssh_public_key_path`.
- The example convention is `/root/.ssh/ansible_ssh_key.pub`.
- The repository does not generate or manage the controller private key.
- The controller's private-key `IdentityFile` is an operator SSH-config concern and must stay outside the inventory shortcut block managed by `controller_ssh_config`.
- Remote servers store public-key content in `authorized_keys`; they do not depend on the controller-side key filename.

## Validation Rules

GitHub Actions is the authoritative repository-validation environment. Contributors and agents are not required to install Python, Ansible, lint tooling, or Galaxy collections on the Ansible controller merely to validate a PR.

Before declaring a repository change ready for merge:

1. Review the complete diff.
2. Confirm no unrelated files changed.
3. Confirm no secrets, real inventory, private keys, or production values were introduced.
4. Push the feature/fix branch and allow the repository CI workflow to run.
5. Require the `CI Gate` status to pass before merge, including the mandatory `Secret Scan` job.
6. Treat local `./scripts/validate.sh` execution as optional developer convenience, not a merge requirement.
7. For promotion to `main`, require Full Release Qualification to pass in addition to the normal CI jobs.
8. State clearly which production tests remain operator-only.

The CI workflow installs its own pinned validation toolchain, uses only sanitized/example fixtures, and must never contact production hosts. The pinned secret scanner examines repository history without using production credentials. `CI Gate` always requires repository validation, Secret Scan, and core Molecule integration. On `development`, `main`, and PRs targeting `main`, it also requires Full Release Qualification. Full Release Qualification may use disposable privileged containers, but must not use production credentials, provider APIs, or production hosts.

## Operator-only safety boundaries

- Upstream FloatIP and native Port Forward Manager releases currently publish no checksum/signature assets. GitHub Release tag validation, HTTPS downloads, and syntax checks are **not** independent artifact authenticity verification. Do not claim checksum enforcement exists until a trusted release manifest/signature and verification mechanism are implemented.
- CI fault contracts check bounded APT-lock waits, SSH reconnection and reboot timeout policies, and fail-closed release metadata handling. They are not a substitute for live fault injection against real servers.
- Follow the test scope and remaining gaps in `docs/operational-hardening.md`.
- For automatic Bootstrap and one-time Marker adoption use `docs/auto-bootstrap.md`. Never auto-run Bootstrap just because a file is missing.

## Change Workflow

1. Inspect the current implementation and documentation.
2. Identify actual behavior and dependencies.
3. Make the smallest coherent change that satisfies the request.
4. Preserve production behavior unless the request explicitly changes it.
5. Commit only on the feature/fix branch.
6. Open a PR to `development` when requested.
7. Use GitHub Actions as the required repository-validation gate.
8. Stop and report; the operator performs the merge and production validation.

## Communication

- Be concise and specific.
- List files changed.
- State validation commands or checks performed.
- Identify remaining operator-only verification.
- Never claim production behavior was verified unless the operator actually tested it.
