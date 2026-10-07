# Changelog

All notable changes to this project are documented in this file.

The project follows Semantic Versioning for published releases.

## [Unreleased]

## [1.0.0] - 2026-10-08

First stable release of the Ansible infrastructure automation project.

### Added

- Production-oriented Ansible architecture for multi-node Linux infrastructure.
- Secure SSH bootstrap, public-key deployment, SSH hardening, and controller-side SSH shortcut management.
- Cloudflare DNS management with unique A-record enforcement.
- Hostname and systemd-resolved configuration.
- Baseline package management and pinned operational tooling.
- Docker Engine installation from the official Docker repository.
- PasarGuard node installation, configuration, certificate retrieval, and memory watchdog automation.
- Prometheus Node Exporter deployment and inventory-driven Prometheus target generation.
- Abuse Firewall automation for selected hosts.
- Pinned Ookla Speedtest CLI installation.
- Pinned FloatIP Manager installation on detected Hetzner hosts, without coupling Ansible to live Floating IP management.
- Independent operational playbooks for system updates, security updates, ICMP control, and native network optimization.
- Native RAM-aware network optimization with BBR, conntrack, TCP buffer, backlog, file-limit, RPS/RFS/XPS, journald, NTP, and swap-aware tuning.
- Ansible check-mode support and non-regressive safety checks for optimization.
- Automatic security patching with `unattended-upgrades`.
- Explicit `needrestart` policy protecting critical network-manager services from unattended restarts.
- GitHub Actions CI with pinned validation dependencies.
- Repository safety checks, YAML linting, Ansible linting, syntax checks, sanitized inventory validation, and generated-configuration validation.
- Molecule integration and idempotency testing on Ubuntu 24.04 and Ubuntu 26.04.
- Full Release Qualification using disposable systemd-enabled containers.
- Release qualification coverage for SSH, resolver, monitoring, FloatIP installer behavior, Speedtest installer behavior, PasarGuard mock installation, watchdog, Abuse Firewall, security updates, and system updates.
- Contract tests for Cloudflare, Docker, FloatIP separation, playbook topology, and optimization non-goals.
- Synthetic optimization capacity tests for S, M, L, and XL memory tiers.
- Rendered artifact validation with Bash syntax checks, ShellCheck, and `systemd-analyze verify`.
- Protected `development` and `main` workflows with required pull requests and required `CI Gate` status checks.
- Public repository sanitization and example inventory/Vault files for safe portfolio use.

### Changed

- Replaced legacy ServerTools-based tuning with repository-owned native Ansible optimization.
- Kept optimization separate from `site.yml` as an explicit operational action.
- Made GitHub Actions the authoritative repository-validation environment; local validation is optional.
- Hardened monitoring target generation to fall back to inventory hostnames when `ansible_host` is not defined.
- Made Abuse Firewall host-file updates compatible with bind-mounted filesystems while retaining normal Ansible behavior elsewhere.
- Improved generated optimization and firewall scripts to pass ShellCheck without changing their intended runtime behavior.

### Security

- Disabled password-based SSH access in normal managed state.
- Preserved automatic security package installation while keeping automatic reboot disabled by default.
- Protected `systemd-networkd.service`, `networking.service`, and `NetworkManager.service` from unattended `needrestart` restarts.
- Prevented production inventory, Vault data, private keys, and credentials from being tracked by repository validation.
- Kept GitHub Actions read-only with no production credentials, provider API tokens, or production host connectivity.
- Blocked force-pushes and protected-branch deletion through repository rulesets.

### Validation

- Native optimization validated on canary hosts and rolled out across the fleet with idempotent reruns.
- Security-update hardening validated on a canary host and rolled out across the fleet with idempotent reruns.
- Full release qualification passed on disposable Ubuntu 24.04 and Ubuntu 26.04 environments.
- Production `site.yml` rollout completed successfully with no failed or unreachable hosts.

### Operational Notes

- Production deployment remains operator-controlled and is intentionally separate from GitHub Actions.
- Cloudflare provider changes and real kernel/network optimization behavior remain production/canary responsibilities rather than CI-side actions.
- FloatIP Manager installation is independent from live Floating IP configuration by design.

[Unreleased]: https://github.com/h-zare-dev/ansible-infrastructure-automation/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/h-zare-dev/ansible-infrastructure-automation/releases/tag/v1.0.0
