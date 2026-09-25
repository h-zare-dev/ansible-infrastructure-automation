# AGENTS.md

## Purpose

This repository manages production-oriented Ansible infrastructure.

Agents working in this repository must prioritize safety, clarity, maintainability, and preservation of existing production behavior.

## Engineering Principles

- SRP: each Ansible role must have one clear responsibility.
- SOLID: prefer small, composable, well-scoped units.
- KISS: avoid unnecessary abstraction and complexity.
- DRY: shared behavior must be implemented once and reused.
- Idempotency: tasks should report `ok` when no state change is required.
- Explicit orchestration: playbooks coordinate roles; role logic belongs in roles.
- Preserve existing behavior unless a change is explicitly requested.
- Prefer small, reviewable commits over large refactors.
- Avoid unrelated cleanup in the same commit.

## Production Safety Rules

These rules are mandatory:

- Never SSH to production infrastructure hosts.
- Never execute Ansible against production hosts.
- Never use or request production passwords, API keys, Vault secrets, private keys, or tokens.
- Never read production inventory or production Vault files if they are not already part of the repository.
- Never modify production inventory.
- Never modify Git remotes.
- Never configure Git credentials.
- Never push.
- Never force-push.
- Never merge branches.
- Never rebase shared branches.
- Never delete branches.
- Never checkout `main`.
- Never checkout `refactor/development`.
- Work only on the current feature branch.
- Stop when an unexpected failure occurs and report it.

Production deployment and validation are performed manually by the operator.

## Git Rules

- Work only on the current feature branch.
- Commit locally only.
- Do not push or merge.
- Keep commits small and focused.
- Use clear commit messages.
- Do not rewrite published history.
- Do not amend earlier commits unless explicitly instructed.
- Before committing, inspect `git diff` and `git status`.
- Never include secrets, credentials, real production inventory, private keys, or Vault passwords.

## Ansible Design Rules

- Every role should have one clear responsibility.
- Do not create generic catch-all roles such as `common` when responsibilities can be named explicitly.
- Prefer role names that describe the responsibility directly.
- Keep operational playbooks separate from desired-state orchestration unless explicitly requested otherwise.
- Reuse the same role from multiple playbooks instead of duplicating tasks.
- Preserve existing host targeting and group behavior unless the task explicitly changes it.
- Prefer built-in Ansible modules over `shell` or `command` when practical.
- Preserve idempotency.
- Use `delegate_to`, `run_once`, handlers, tags, and variables intentionally.
- Avoid hidden side effects.
- Do not silently change reboot behavior, SSH access, firewall policy, package upgrades, DNS behavior, or monitoring behavior.

## Existing Behavioral Contracts

- `bootstrap.yml` is used for initial server onboarding.
- `site.yml` is the main desired-state playbook.
- SSH hardening remains reusable and idempotent.
- Optimization is part of `site.yml` and also has an independent operational playbook.
- `security-updates.yml` remains an independent operational playbook.
- `system-update.yml` remains an independent operational playbook.
- `ping-control.yml` remains an independent operational playbook.
- Monitoring target generation must remain inventory-driven.
- Public repository files must remain sanitized.
- Real inventory and real Vault files must remain excluded from Git.

## Validation Rules

Before declaring a change complete:

1. Run `git diff --check`.
2. Run syntax checks for all playbooks affected by the change.
3. Review `git diff`.
4. Confirm that no unrelated files changed.
5. Confirm that no secrets or production values were introduced.
6. Confirm that existing operational playbooks still exist and remain reachable.
7. Report what changed, what was validated locally, and what still requires production testing.

Do not run production deployment tests.

## Refactor Workflow

For each refactor phase:

1. Inspect the current implementation.
2. Identify existing behavior and dependencies.
3. Make the smallest structural change that achieves the phase goal.
4. Preserve behavior.
5. Validate locally.
6. Commit locally.
7. Stop and report results.

Do not proceed to the next phase unless explicitly instructed.

## Communication

- Be concise and specific.
- List files changed.
- State validation commands executed.
- State whether validation passed.
- Identify any uncertainty or production-only verification still required.
- Never claim production behavior was verified unless the operator actually tested it.
