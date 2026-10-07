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

Production deployment and validation are performed manually by the operator.

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
  - It clears only the selected target's stale controller host-key entries.
  - The remote role order is `system_update`, `speedtest_cli`, `floatip_manager`, `ssh_security`, `cloudflare_dns`, `controller_ssh_config`.
- `site.yml` is the main desired-state workflow.
  - The all-host play includes SSH/controller config, Cloudflare DNS, hostname, resolver, base packages, Speedtest CLI, FloatIP manager, and monitoring.
  - PasarGuard-specific roles remain scoped to `pasarguard_nodes`.
- `floatip_manager` installs only on hosts detected as Hetzner and must not change floating addresses merely by being installed.
- `optimization` runs only through `playbooks/operations/optimize.yml`; it is not part of `site.yml`.
  - The default host pattern is `common`.
  - `optimize_hosts` can explicitly override that pattern.
  - The repository-owned native role must keep its pre/post network and Docker safety assertions.
  - Normal converged runs are expected to be idempotent and `--check --diff` must remain non-mutating.
- `security-updates.yml`, `system-update.yml`, and `ping-control.yml` remain independent operational playbooks.
- `security_updates` keeps unattended security installation enabled while automatic reboot remains disabled by default.
  - `needrestart` may restart ordinary services automatically, but critical network-manager services are excluded by default and deferred to controlled maintenance.
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

Before declaring a repository change complete:

1. Run or arrange `git diff --check`.
2. Run `./scripts/validate.sh` when the working environment can execute it safely.
3. Syntax-check all affected playbooks.
4. Review the complete diff.
5. Confirm no unrelated files changed.
6. Confirm no secrets, real inventory, private keys, or production values were introduced.
7. Confirm required operational playbooks still exist and remain reachable.
8. State clearly which validation was automated and which production tests are still operator-only.

Do not contact production hosts for validation.

## Change Workflow

1. Inspect the current implementation and documentation.
2. Identify actual behavior and dependencies.
3. Make the smallest coherent change that satisfies the request.
4. Preserve production behavior unless the request explicitly changes it.
5. Validate locally or with repository CI when available.
6. Commit only on the feature/fix branch.
7. Open a PR to `development` when requested.
8. Stop and report; the operator performs the merge and production validation.

## Communication

- Be concise and specific.
- List files changed.
- State validation commands or checks performed.
- Identify remaining operator-only verification.
- Never claim production behavior was verified unless the operator actually tested it.
