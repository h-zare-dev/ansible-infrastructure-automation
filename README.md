# Ansible Infrastructure Automation

Production-oriented Ansible project for provisioning, securing, monitoring, and operating a multi-node Linux infrastructure.

This repository uses focused Ansible roles for SSH access, DNS and baseline Linux setup, pinned operational tooling, Docker, Prometheus monitoring, PasarGuard nodes, watchdog automation, firewall controls, native network tuning, and controlled maintenance.

The project is designed around two distinct workflows:

1. **Initial server onboarding** — establish SSH access, create a Cloudflare DNS record, and update controller SSH shortcuts.
2. **Ongoing desired-state management** — repeatedly apply configuration safely and idempotently.

System upgrades, security update policy, ICMP control, and optimization are explicit independent operations.

---

## Highlights

- Secure first-time SSH bootstrap using credentials stored in Ansible Vault
- Public-key SSH authentication and hardened SSH configuration
- Idempotent SSH policy enforcement on every normal deployment
- Cloudflare DNS records managed by the same role during bootstrap and normal deployment
- Inventory-derived SSH shortcuts on the Ansible controller
- Centralized inventory and functional host grouping
- Automated hostname and DNS configuration
- Baseline packages, including `cron` for the watchdog
- Docker Engine installation from the official Docker repository
- Prometheus Node Exporter deployment
- Dynamic Prometheus target generation directly from Ansible inventory
- Prometheus target directory management compatible with Docker directory mounts
- Application-node provisioning and configuration
- Memory watchdog deployment and cron scheduling
- Firewall automation for selected host groups
- Controlled rolling system upgrades with automatic reboot detection
- Automatic security patching with `unattended-upgrades`
- Automatic reboot disabled for unattended security updates
- Independent operational playbooks for system updates, security updates, ping control, and native network optimization
- Pinned Ookla Speedtest CLI installation on supported hosts
- Pinned `floatip-manager` installation on detected Hetzner hosts
- RAM-aware, non-regressive BBR/conntrack/TCP tuning with Ansible check-mode support
- Ansible Vault integration for secrets and environment-specific values
- Public repository sanitization for safe portfolio use
- Local linting and syntax validation with sanitized example inventory

---

## Repository Structure

```text
ansible-infrastructure-automation/
├── .ansible-lint
├── .ansible-lint-ignore
├── .yamllint
├── AGENTS.md
├── ansible.cfg
├── requirements-dev.txt
├── requirements.yml
├── docs/
│   ├── native-vpn-optimization.md
│   └── refactor-plan.md
├── inventory/
│   ├── hosts.example.ini
│   └── group_vars/
│       ├── all/
│       │   ├── vars.yml
│       │   └── vault.yml.example
│       └── ssh_ubuntu.yml
├── playbooks/
│   ├── bootstrap.yml
│   ├── security.yml
│   ├── site.yml
│   └── operations/
│       ├── optimize.yml
│       ├── ping-control.yml
│       ├── security-updates.yml
│       └── system-update.yml
├── scripts/
│   └── validate.sh
└── roles/
    ├── abuse_firewall/
    ├── base_packages/
    ├── cloudflare_dns/
    ├── controller_known_hosts/
    ├── controller_ssh_config/
    ├── dns_resolver/
    ├── docker/
    ├── floatip_manager/
    ├── hostname/
    ├── monitoring/
    ├── optimization/
    ├── pasarguard/
    ├── pasarguard_watchdog/
    ├── security_updates/
    ├── speedtest_cli/
    ├── ssh_security/
    └── system_update/
```

Production inventory, Vault data, Vault password files, private keys, and credentials are excluded from version control.

---

# Deployment Model

## Fresh Server Onboarding

A newly created server may initially allow only password-based SSH access.

In that state, `site.yml` cannot be expected to work immediately because normal Ansible access is configured for key-based authentication.

The correct onboarding sequence is:

```text
Fresh server
  → add host to inventory
  → bootstrap.yml
      → controller_known_hosts (controller-side cleanup before remote fact gathering)
      → system_update (reboot when required)
      → speedtest_cli
      → floatip_manager (Hetzner hosts only)
      → ssh_security
      → cloudflare_dns
      → controller_ssh_config
  → site.yml
      → focused desired-state role orchestration
```

### Step 1 — Add the host to inventory

Add the new server to the appropriate inventory group.

Example:

```ini
[pasarguard_nodes]
node-01 ansible_host=192.0.2.10
```

Use the correct connection variables for the environment.

### Step 2 — Bootstrap the server and controller access

Run:

```bash
ansible-playbook playbooks/bootstrap.yml \
  -e bootstrap_host=node-01
```

`bootstrap.yml` targets `bootstrap_host`. Its first play disables fact gathering and runs `controller_known_hosts` entirely on localhost, before any SSH connection to the server. It uses `ssh-keygen -F` and `ssh-keygen -R` to remove only that target's entries from the controller user's `~/.ssh/known_hosts`, including hashed entries. It checks both `ansible_host` (falling back to the inventory hostname) and the inventory hostname, including its lowercase SSH alias. For a nonstandard `ansible_port`, it also checks `[hostname]:port` and `[IP]:port` entries. Missing files or matching entries require no changes.

The remote bootstrap play uses Vault-provided SSH and privilege-escalation passwords. Its current role order is `system_update`, `speedtest_cli`, `floatip_manager`, `ssh_security`, `cloudflare_dns`, `controller_ssh_config`:

- `system_update` performs the platform-aware update and may reboot when the host reports that a reboot is required.
- `speedtest_cli` installs the pinned Ookla Speedtest CLI on the currently supported architecture.
- `floatip_manager` installs the pinned `floatip` command only when Ansible detects a Hetzner system vendor; it does not add or remove addresses during installation.
- `ssh_security` installs the managed public key, applies SSH hardening, and restarts SSH when its configuration changes.
- `cloudflare_dns` creates or updates the host's Cloudflare A record.
- `controller_ssh_config` updates the controller user's SSH shortcuts from the complete inventory, even though bootstrap targets only one host.

### Step 3 — Run the main deployment

After bootstrap succeeds:

```bash
ansible-playbook playbooks/site.yml \
  --limit node-01
```

At this point key-based SSH authentication, the DNS record, and the controller shortcut are in place for normal desired-state deployment.

---

# Why SSH Security Exists in Both Bootstrap and Site

The `ssh_security` role intentionally appears in both workflows.

### In `bootstrap.yml`

Its purpose is to establish trusted SSH access for the first time.

### In `site.yml`

Its purpose is to continuously enforce the desired SSH security policy.

This is intentional and not duplicate work.

Because the role is idempotent, a correctly configured server should normally produce `ok` instead of unnecessary changes on later runs.

This supports both cases:

- a fresh password-only server can be onboarded safely
- an already managed server remains compliant if SSH configuration is changed manually later
---

# Cloudflare DNS Reuse

`cloudflare_dns` is the same role in `bootstrap.yml` and `site.yml`. It manages each host's Cloudflare A record from its lowercase inventory name and `ansible_host`, with the zone supplied by `domain_suffix`. The DNS task is delegated to the controller; neither playbook duplicates its logic. API credentials remain in Vault-backed variables.

---

# Main Playbook

## `site.yml`

`site.yml` is the primary desired-state configuration entry point. It has two logical plays with separate, single-responsibility roles:

1. **All managed servers** — gathers facts once, then runs `ssh_security`, `controller_ssh_config`, `cloudflare_dns`, `hostname`, `dns_resolver`, `base_packages`, `speedtest_cli`, `floatip_manager`, and `monitoring` in that order. `floatip_manager` is conditional on Hetzner detection. Controller SSH shortcuts and monitoring targets are generated on the controller.
2. **`pasarguard_nodes`** — sets `gather_facts: false` and runs `docker`, `pasarguard`, and `pasarguard_watchdog`, followed by `abuse_firewall` only for hosts also in `abuse_protected`.

An inventory host runs only the plays whose host groups include it. `all` includes inventory hosts without requiring an explicit `[all]` section. DNS resolver configuration belongs to `dns_resolver`; the native `optimization` role deliberately leaves DNS untouched.

Run on all applicable managed hosts:

```bash
ansible-playbook playbooks/site.yml
```

Run on only one host:

```bash
ansible-playbook playbooks/site.yml \
  --limit SERVER_NAME
```

Optimization, full system upgrades, ICMP policy changes, and security-update policy rollout remain separate operational actions.

---

# Other Playbooks

## `bootstrap.yml`

SSH, Cloudflare DNS, and controller SSH shortcut onboarding for a new or rebuilt server. Bootstrap clears the selected target's controller host-key entries before connecting; `site.yml` does not run this cleanup.

```bash
ansible-playbook playbooks/bootstrap.yml \
  -e bootstrap_host=SERVER_NAME
```

Use this before `site.yml` when the server does not yet accept the managed SSH key.

## `security.yml`

Re-applies SSH hardening independently from the full deployment.

```bash
ansible-playbook playbooks/security.yml
```

Useful when SSH policy needs to be enforced without running unrelated roles.

---

# Operational Playbooks

System upgrades, security-update policy, ping control, and optimization are independent of `site.yml`.

```text
playbooks/operations/
├── optimize.yml
├── ping-control.yml
├── security-updates.yml
└── system-update.yml
```

Keeping these operations separate avoids adding them to ordinary configuration runs.

## Controlled System Updates

`playbooks/operations/system-update.yml` performs controlled package maintenance on `pasarguard_nodes`.

It:

- refreshes the APT package cache
- performs distribution upgrades
- removes unused dependencies
- cleans obsolete package files
- checks `/var/run/reboot-required`
- reboots only when required

The playbook uses:

```yaml
serial: 1
```

This means servers are processed one at a time.

That behavior reduces the risk of taking multiple production nodes offline simultaneously.

Run:

```bash
ansible-playbook playbooks/operations/system-update.yml
```

To test on one host first:

```bash
ansible-playbook playbooks/operations/system-update.yml \
  --limit SERVER_NAME
```

This playbook is intentionally **not** part of `site.yml`.

## Automatic Security Updates

`playbooks/operations/security-updates.yml` applies the `security_updates` role to `pasarguard_nodes`, one host at a time.

It configures Ubuntu automatic security patching using `unattended-upgrades`.

The role:

- installs `unattended-upgrades`
- installs `apt-listchanges`
- enables periodic package-list refreshes
- enables unattended security updates
- limits automatic installation to security updates
- disables automatic rebooting

Automatic reboot is intentionally disabled.

Reboots remain a controlled maintenance operation and can be handled through `system-update.yml`.

Run:

```bash
ansible-playbook playbooks/operations/security-updates.yml
```

This playbook is intentionally separate from `site.yml`.

## Optimization

Optimization is run only through `playbooks/operations/optimize.yml`; it is not applied by `site.yml`. The playbook defaults to the `common` inventory group and accepts an explicit `optimize_hosts` host-pattern override.

```bash
ansible-playbook playbooks/operations/optimize.yml

# Preview without applying changes
ansible-playbook playbooks/operations/optimize.yml --check --diff

# Override the play target for a canary that is outside `common`
ansible-playbook playbooks/operations/optimize.yml \
  -e optimize_hosts=Test-DE
```

The repository now owns the complete `optimization` role; it no longer downloads or executes ServerTools. The role selects RAM-aware S/M/L/XL capacity tiers, preserves already-higher kernel capacity values, can incorporate `optimization_expected_users`, configures supported BBR/qdisc settings, manages file-descriptor and optional CPU/NIC tuning, caps journald, enables NTP when available, and safely retires conflicting files from the former ServerTools integration.

Before and after tuning it verifies critical live sysctls and checks that the default route, interface IPv4 address set, resolver file, live qdisc (unless explicitly opted in), and running Docker container set were not unexpectedly changed. Normal repeat runs are designed to be idempotent; check mode uses read-only probes and predicts supported kernel modules without loading them.

See [`docs/native-vpn-optimization.md`](docs/native-vpn-optimization.md) for the exact scope, safety boundaries, capacity tiers, check-mode behavior, and validation workflow.

## ICMP / Ping Control

`playbooks/operations/ping-control.yml` manages ICMP behavior for `all` independently from the main deployment. Its default action is `allow`; operators can set `ping_action=block` when needed.

```bash
ansible-playbook playbooks/operations/ping-control.yml
```

This is also intentionally excluded from `site.yml`.

---

# Role Responsibilities

The former `common` role was split into focused responsibilities. Current roles are:

| Role | Responsibility |
| --- | --- |
| `ssh_security` | Install the managed SSH public key and enforce server SSH policy. |
| `controller_known_hosts` | Remove only the bootstrap target's stale controller `known_hosts` entries before first connection. |
| `controller_ssh_config` | Maintain inventory-derived SSH shortcuts on the controller. |
| `cloudflare_dns` | Manage the host's Cloudflare A record from inventory. |
| `hostname` | Set the lowercase inventory name as the system hostname. |
| `dns_resolver` | Configure systemd-resolved DNS and restart it when needed. |
| `base_packages` | Install the baseline APT packages. |
| `speedtest_cli` | Install pinned Ookla Speedtest CLI 1.2.0; currently validates `x86_64`. |
| `floatip_manager` | Install the pinned `floatip` command on detected Hetzner hosts without changing addresses during installation. |
| `monitoring` | Install Node Exporter and generate inventory-driven Prometheus targets. |
| `docker` | Install and start Docker Engine and its plugins. |
| `pasarguard` | Install and configure the PasarGuard node. |
| `pasarguard_watchdog` | Deploy the memory watchdog and schedule it with cron. |
| `abuse_firewall` | Deploy selected-host firewall updates and a daily refresh job. |
| `optimization` | Apply repository-owned native network-host tuning and verification. |
| `security_updates` | Configure unattended security updates through its operational playbook. |
| `system_update` | Perform platform-aware package maintenance and optional reboot handling. |

`base_packages` installs exactly:

```text
btop
curl
cron
```

`cron` is a baseline dependency because the watchdog role uses the `crontab` executable.

The first `site.yml` play runs `base_packages` before the watchdog role in the second play.

---

# Controller SSH Shortcuts

`controller_ssh_config` maintains SSH shortcuts in the SSH config under the Ansible controller user's `HOME`. It runs once on the controller. It renders every host in `groups['all'] | sort`, including hosts outside the current bootstrap target, so each inventory host appears once in a deterministic order.

Aliases and DNS hostnames use lowercase inventory names. For example, inventory name `Node-01` produces the shortcut `ssh node-01` and a `HostName` of `node-01.<domain_suffix>`. The `User` entry comes from `hostvars[host].ansible_user`, falling back to `root` if it is undefined. The `ssh_ubuntu` inventory group supplies `ubuntu` for its members.

The role safely handles a missing SSH config in both normal and check-mode runs. A normal run creates the file before reading and managing it; check mode validates the missing-file case without requiring the file to be written. It owns one clearly marked block in the config, placing it after global directives and before the first `Host` or `Match` section so inventory-specific values can precede generic options such as `Host *`. It does not rewrite unrelated manual entries, `Include` directives, comments, or formatting. A manually defined alias that conflicts case-insensitively with an inventory alias causes a clear failure; the role does not overwrite it. It also rejects inventory names that would produce duplicate lowercase aliases.

Adding or removing inventory hosts, or changing their `ansible_user`, updates only the managed block. Repeating the same run leaves it unchanged. The role does not manage private keys or SSH server configuration; bootstrap host-key cleanup belongs to the separate `controller_known_hosts` role.

The managed block also does not own a controller `IdentityFile`. If the controller uses the project convention of `~/.ssh/ansible_ssh_key`, keep that setting outside the Ansible-managed inventory block, for example:

```ssh
Host *
  IdentityFile ~/.ssh/ansible_ssh_key
```

The public half is read from the controller path referenced by `vault_ssh_public_key_path` and copied into the remote user's `authorized_keys`. Renaming the controller key files therefore requires updating the local SSH `IdentityFile` for the private key and the Vault path for the `.pub` file; remote servers do not store or depend on the controller-side filename.

---

# Operational Tools Installed on Managed Hosts

## Ookla Speedtest CLI

`speedtest_cli` installs Ookla Speedtest CLI version `1.2.0` at `/usr/local/bin/speedtest` from the pinned role defaults. The archive is cached under `/var/cache/ookla-speedtest/<version>`. The current role intentionally validates `x86_64`; unsupported architectures fail clearly instead of silently installing the wrong binary.

## Floating IP Manager

`floatip_manager` installs a commit-pinned copy of `h-zare-dev/floatip-manager` as `/usr/local/sbin/floatip` only on hosts whose detected system vendor contains `hetzner`. Installation itself does not add, delete, or replace any floating IP. Address management remains an explicit operator action through the installed command.

---

# Monitoring

The `monitoring` role installs and starts Prometheus Node Exporter on managed hosts.

It also generates Prometheus file-service-discovery targets dynamically from the Ansible inventory.

This keeps monitoring discovery aligned with infrastructure state rather than requiring a second manually maintained server list.

## Prometheus Target Path

By default, the generated target file is stored on the controller at:

```text
/opt/monitoring/targets/targets.json
```

The monitoring role ensures that the parent directory exists before generating the file. Set `monitoring_targets_dir` in normal group vars to change the controller output directory; the filename remains `targets.json`.

Example directory structure:

```text
/opt/monitoring/
├── docker-compose.yml
├── prometheus.yml
└── targets/
    └── targets.json
```

The Prometheus Docker Compose configuration mounts the entire target directory:

```yaml
volumes:
  - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
  - ./targets:/etc/prometheus/targets:ro
```

Prometheus then reads:

```text
/etc/prometheus/targets/targets.json
```

Example Prometheus configuration:

```yaml
scrape_configs:
  - job_name: 'marzban_nodes'
    file_sd_configs:
      - files:
          - '/etc/prometheus/targets/targets.json'
```

### Why a Directory Mount Is Used

The target directory is mounted instead of bind-mounting a single generated file.

Ansible's template module updates files atomically. With a direct single-file Docker bind mount, a container can continue referencing the previous inode after the host file is replaced.

Mounting the parent directory avoids this issue and allows Prometheus to observe the updated target file correctly.

As a result, adding a new inventory host and running the monitoring role updates the correct file without requiring Grafana to be restarted.

Grafana reads metrics from Prometheus and does not need direct access to the target file.

---

# Docker Provisioning

The `docker` role:

- installs required dependencies
- creates the Docker keyring directory
- installs the Docker GPG key
- configures the official Docker repository
- installs Docker Engine
- installs Docker Buildx
- installs the Docker Compose plugin
- enables and starts Docker

Docker provisioning is applied to application nodes rather than every inventory host.

---

# Application Node Provisioning

The `pasarguard` role handles node installation and configuration.

The workflow includes:

- installer execution
- API configuration
- SAN/certificate configuration
- service protocol enforcement
- service restart when configuration changes
- SSL certificate retrieval to the controller

The controller-side certificate destination is configured independently through `pasarguard_cert_destination_dir` in normal group vars (default: `/opt/pasarguard/certs`). Certificates do not need to be stored under `/opt/monitoring`.

The installation task uses Ansible state checks to avoid unnecessary repeated installations.

Sensitive installer output should be handled carefully because command output can expose credentials if logging is enabled.

---

# Memory Watchdog

The `pasarguard_watchdog` role deploys a memory-watchdog script and schedules it through cron.

Because minimal servers may not include `crontab` by default, `base_packages` installs `cron` before the watchdog role runs in `site.yml`.

---

# Firewall Automation

Firewall rules are applied only to hosts in the dedicated inventory group:

```text
abuse_protected
```

In the second `site.yml` play, `abuse_firewall` runs after Docker, PasarGuard, and the watchdog only when a `pasarguard_nodes` host also belongs to that group.

This allows security controls to be enabled selectively without applying the same network policy to every managed node.

---

# Inventory Design

The public example inventory demonstrates functional host grouping.

Current groups include:

- `all` — every inventory host; Ansible provides this group without an explicit `[all]` section
- `common` — default target group for the standalone native optimization playbook
- `pasarguard_nodes` — application nodes managed by the main deployment
- `ssh_ubuntu` — hosts accessed through an `ubuntu` user with privilege escalation
- `abuse_protected` — hosts receiving additional firewall protection

Production inventory values are intentionally excluded from the public repository.

Real provider names, addresses, infrastructure details, and credentials should remain in the ignored local inventory.

---

# Secrets and Ansible Vault

Environment-specific and sensitive values are referenced through Ansible Vault.

Examples include:

- bootstrap passwords
- privilege-escalation credentials
- API credentials- domain configuration
- controller-side SSH public-key path
- external provider tokens

The public repository contains only a safe example:

```text
inventory/group_vars/all/vault.yml.example
```

The example follows the controller key naming convention:

```yaml
vault_ssh_public_key_path: "/root/.ssh/ansible_ssh_key.pub"
```

This variable is a controller-side file path, not a filename that must exist on managed servers.

Create a local production copy:

```bash
cp inventory/group_vars/all/vault.yml.example \
  inventory/group_vars/all/vault.yml
```

Encrypt it:

```bash
ansible-vault encrypt \
  inventory/group_vars/all/vault.yml
```

Production Vault files and Vault password files must not be committed. Keep API credentials and tokens in the ignored Vault data, never in tracked files.

---

# Public Repository Safety

This repository is sanitized for portfolio use.

Public files:

```text
inventory/hosts.example.ini
inventory/group_vars/all/vault.yml.example
```

Local production inventory, Vault data, Vault password files, and SSH private-key patterns are excluded through `.gitignore`. Repository validation uses only sanitized example data. Production deployment and testing are manual, operator-controlled actions.

Never commit:

- real production inventory
- Vault passwords
- decrypted secrets
- private SSH keys
- API tokens
- real infrastructure credentials
- sensitive domains or internal configuration
- command output containing credentials

---

# Dependencies

Use a Python virtual environment for local validation. Install the developer tools and the project's pinned Ansible Galaxy collections:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
ansible-galaxy collection install -r requirements.yml
```

---

# Validation

Run the repository's safe local validation command:

```bash
./scripts/validate.sh
```

It checks Git diff formatting, shows repository status, runs `yamllint` and `ansible-lint`, syntax-checks every playbook, verifies the required operational playbooks, and rejects tracked production inventory or Vault files. Bootstrap syntax checking supplies a safe `bootstrap_host`. Ansible checks use an isolated copy of the example inventory and sanitized group variables, so ignored production files beside the example inventory are not loaded. The command does not contact production hosts.

A few existing task-specific ansible-lint findings are narrowly ignored to preserve production behavior. The existing Docker `apt_repository` deprecation warning is outside this documentation phase.

Production inventory validation, connectivity checks, and deployment testing remain operator-controlled. Do not use the repository's default inventory for local validation.

---

# Reliability and Idempotency

Repeated runs should normally report `ok` for already-correct SSH security, Cloudflare DNS records, hostname, resolver settings, baseline packages, controller SSH shortcuts, and monitoring target generation. Ubuntu SSH-user detection is safe in Ansible check mode. Docker, PasarGuard installation and configuration, and watchdog deployment also use state checks where their implementation supports them.

The native `optimization` operation is also designed for idempotent normal runs and supports `--check --diff`. A first migration run can legitimately report changes while it installs repository-owned tuning files and retires old ServerTools artifacts; once converged, repeated normal runs should report no changes unless the host state or desired variables changed. Local linting and syntax checks validate repository structure; the operator must still verify actual access, DNS, monitoring, networking, and reboot behavior in the production environment.

---

# Recommended New-Server Workflow

For a newly provisioned password-only server:

```bash
# 1. Add the server to inventory

# 2. Bootstrap updates/tooling, SSH, Cloudflare DNS, and controller shortcuts
ansible-playbook playbooks/bootstrap.yml \
  -e bootstrap_host=NEW_SERVER

# 3. Apply normal desired state
ansible-playbook playbooks/site.yml \
  --limit NEW_SERVER

# 4. Configure unattended security patching
ansible-playbook playbooks/operations/security-updates.yml \
  --limit NEW_SERVER

# 5. Run standalone optimization explicitly if needed
ansible-playbook playbooks/operations/optimize.yml \
  --limit NEW_SERVER
```

Full system upgrades remain a separate maintenance decision:

```bash
ansible-playbook playbooks/operations/system-update.yml \
  --limit NEW_SERVER
```

---

# Skills Demonstrated

This project demonstrates hands-on experience with:

- Ansible
- Infrastructure as Code
- Linux server provisioning
- SSH bootstrap and hardening
- Ansible Vault
- privilege escalation
- inventory design
- group-based configuration
- idempotent role design
- package management
- systemd
- DNS automation
- Docker Engine
- Docker Compose
- Prometheus
- Node Exporter
- Grafana integration
- file-based service discovery
- cron automation
- firewall automation
- native BBR/TCP/conntrack capacity tuning
- Ansible check-mode and idempotency validation
- floating/secondary IP tooling
- pinned operational CLI deployment
- controlled rolling maintenance
- automatic security patching
- reboot management
- operational playbook separation
- Git-based infrastructure workflows
- production-safe repository sanitization

---

# Roadmap

Potential future improvements:

- GitHub Actions CI using sanitized example inventory
- secret scanning
- stronger operational timeout handling
- improved APT lock handling
- role-specific documentation
- Molecule testing
- automated idempotency testing
- additional monitoring and alerting
- checksum/signature validation for externally downloaded operational artifacts
- versioned releases and changelog
- further firewall hardening
- staging validation before production rollout

---

# Design Principles

### Bootstrap is separate from normal deployment

Initial trust establishment is different from ongoing configuration management.

### Desired state is repeatable

Normal playbooks should be safe to execute repeatedly.

### Operational maintenance is explicit

System optimization, system upgrades, and other maintenance operations are explicit and separate from `site.yml`.

### Reboots are controlled

Automatic security patching does not automatically reboot production nodes.

### Monitoring follows inventory

Prometheus targets are generated from Ansible inventory instead of being maintained separately.

### Host groups determine responsibility

Application deployment and firewall behavior are applied only where appropriate.

### Secrets stay out of Git

Public repository examples are sanitized and production secrets remain local and encrypted.