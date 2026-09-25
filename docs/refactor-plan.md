# Refactor Plan

## Goal

Refactor the Ansible repository into a cleaner, single-responsibility structure while preserving existing production behavior.

The refactor follows SRP, SOLID, KISS, DRY, and idempotent Ansible practices.

All production testing is performed manually by the operator outside the agent environment.

## Branch Model

```text
main
└── refactor/development
    ├── feature/agent-guardrails
    ├── feature/common-split
    ├── feature/bootstrap-dns
    ├── feature/controller-ssh-config
    ├── feature/playbook-cleanup
    ├── feature/validation
    └── feature/docs
```

Rules:

- Feature branches are created from `refactor/development`.
- Agents work only on the active feature branch.
- Agents commit locally only.
- The operator pushes feature branches manually.
- The operator merges validated feature branches into `refactor/development`.
- `refactor/development` is merged into `main` only after final validation.

## Phase 0 — Agent Guardrails

Branch: `feature/agent-guardrails`

Objectives:

- Add `AGENTS.md`.
- Add this refactor plan.
- Define agent safety rules.
- Define Git safety rules.
- Define production boundaries.
- Define engineering principles.

No infrastructure behavior changes are allowed in this phase.

Expected commit:

```text
Add agent guardrails and refactor plan
```

## Phase 1 — Split the Current Common Role

Branch: `feature/common-split`

Target structure:

```text
roles/
├── base_packages/
├── hostname/
├── dns_resolver/
└── cloudflare_dns/
```

Responsibilities:

- `base_packages`: baseline package installation only.
- `hostname`: system hostname configuration only.
- `dns_resolver`: local resolver configuration only.
- `cloudflare_dns`: Cloudflare DNS record management only.

Requirements:

- Preserve existing behavior.
- Preserve variables and delegation behavior.
- Preserve idempotency.
- Do not alter inventory.
- Do not change secret handling.
- Do not introduce new functionality.
- Remove `common` only after all responsibilities have been migrated safely.

Expected commit:

```text
Refactor common role into focused responsibilities
```

## Phase 2 — Add DNS Provisioning to Bootstrap

Branch: `feature/bootstrap-dns`

Goal:

Reuse the new `cloudflare_dns` role from `bootstrap.yml`.

Target bootstrap flow:

```text
bootstrap.yml
├── ssh_security
└── cloudflare_dns
```

Requirements:

- Reuse the existing `cloudflare_dns` role.
- Do not duplicate Cloudflare tasks.
- Preserve existing bootstrap authentication behavior.
- Preserve SSH hardening behavior.
- Do not add unrelated roles.

Expected commit:

```text
Add DNS provisioning to bootstrap workflow
```

## Phase 3 — Generate Controller SSH Config

Branch: `feature/controller-ssh-config`

Goal:

Generate SSH shortcuts on the Ansible controller from inventory.

New role:

```text
roles/controller_ssh_config/
```

Requirements:

- Use all inventory hosts via `groups['all']`.
- SSH aliases must be lowercase.
- Preserve host-specific `ansible_user`.
- Use the project DNS naming convention.
- Do not overwrite unrelated SSH config entries.
- Prevent duplicate entries.
- Be idempotent.
- A removed inventory host should disappear from the managed block.
- Reuse the role from both `bootstrap.yml` and `site.yml`.
- Do not store or generate private keys.
- Do not modify GitHub credentials.

Target orchestration:

```text
bootstrap.yml
├── ssh_security
├── cloudflare_dns
└── controller_ssh_config
```

```text
site.yml
├── ssh_security
├── cloudflare_dns
├── hostname
├── dns_resolver
├── base_packages
├── controller_ssh_config
├── monitoring
├── docker
├── pasarguard
├── pasarguard_watchdog
├── abuse_firewall
└── optimization
```

Expected commit:

```text
Generate controller SSH config from inventory
```

## Phase 4 — Playbook Orchestration Cleanup

Branch: `feature/playbook-cleanup`

Preserve these operational playbooks:

```text
playbooks/operations/
├── optimize.yml
├── ping-control.yml
├── security-updates.yml
└── system-update.yml
```

Behavioral requirements:

- `optimization` remains in `site.yml`.
- `optimize.yml` remains independently executable.
- `security-updates.yml` remains independent.
- `system-update.yml` remains independent.
- `ping-control.yml` remains independent.
- Do not silently move system update or security update behavior into `site.yml`.
- Do not change reboot behavior.
- Do not change host group targeting unless explicitly required.

Expected commit:

```text
Clean up playbook orchestration after role refactor
```

## Phase 5 — Validation and Linting

Branch: `feature/validation`

Goals:

- Add `ansible-lint`.
- Add `yamllint`.
- Add local validation workflow.
- Add syntax checks for all playbooks.
- Add safe checks that do not contact production hosts.

Expected commit:

```text
Add Ansible linting and local validation
```

## Phase 6 — Documentation

Branch: `feature/docs`

README should document:

- role responsibilities
- fresh-host onboarding
- bootstrap flow
- site flow
- controller SSH config generation
- lowercase SSH aliases
- Cloudflare DNS reuse
- operational playbooks
- optimization behavior
- production safety
- idempotency expectations
- repository sanitization

Do not document behavior that has not been implemented.

Expected commit:

```text
Update documentation for refactored architecture
```

## Final Validation Before Merging to Main

Before `refactor/development` is merged into `main`, the operator should validate the branch against the real environment from an isolated production-side test worktree or clone.

Recommended checks:

1. `git diff --check`
2. syntax checks for all playbooks
3. inventory validation
4. fresh-host bootstrap test
5. Cloudflare DNS creation
6. controller SSH shortcut generation
7. full `site.yml` test on a canary host
8. repeat run to inspect idempotency
9. monitoring target generation
10. Docker role
11. application provisioning
12. watchdog scheduling
13. optimization
14. operational playbooks remain present and syntactically valid
15. no secrets tracked
16. no unrelated changes
17. final fleet test if appropriate

Only after successful validation:

```text
refactor/development → main
```

The agent must never perform this merge.
