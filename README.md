# Ansible Infrastructure Automation

Production-oriented Ansible project for provisioning, securing, monitoring, and operating a multi-node Linux infrastructure.

This repository demonstrates a practical Infrastructure-as-Code workflow built around reusable Ansible roles, secure first-time bootstrap, SSH hardening, common Linux configuration, Docker provisioning, Prometheus monitoring, application-node deployment, watchdog automation, firewall controls, controlled maintenance, and automatic security patching.

The project is designed around two distinct workflows:

1. **Initial server onboarding** — establish trusted SSH access to a fresh server.
2. **Ongoing desired-state management** — repeatedly apply configuration safely and idempotently.

Operational maintenance tasks such as system upgrades, security update configuration, optimization, and ICMP control are intentionally kept separate from the main deployment.

---

## Highlights

- Secure first-time SSH bootstrap using credentials stored in Ansible Vault
- Public-key SSH authentication and hardened SSH configuration
- Idempotent SSH policy enforcement on every normal deployment
- Centralized inventory and functional host grouping
- Automated hostname and DNS configuration
- Common package management, including required runtime dependencies such as `cron`
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
- Operational playbooks kept separate from normal desired-state deployment
- Ansible Vault integration for secrets and environment-specific values
- Public repository sanitization for safe portfolio use
- Tested end-to-end onboarding of newly provisioned servers

---

## Repository Structure

```text
ansible-infrastructure-automation/
├── ansible.cfg
├── requirements.yml
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
└── roles/
    ├── abuse_firewall/
    ├── common/
    ├── docker/
    ├── monitoring/
    ├── optimization/
    ├── pasarguard/
    ├── pasarguard_watchdog/
    ├── security_updates/
    └── ssh_security/
```

Production inventory, encrypted Vault data, Vault passwords, real infrastructure addresses, domains, and credentials are intentionally excluded from version control.

---

# Deployment Model

## Fresh Server Onboarding

A newly created server may initially allow only password-based SSH access.

In that state, `site.yml` cannot be expected to work immediately because normal Ansible access is configured for key-based authentication.

The correct onboarding sequence is:

```text
Fresh server
    ↓
Add host to inventory
    ↓
bootstrap.yml
    ↓
SSH key installed
SSH hardening applied
    ↓
site.yml
    ↓
Normal desired-state configuration
```

### Step 1 — Add the host to inventory

Add the new server to the appropriate inventory group.

Example:

```ini
[pasarguard_nodes]
new-node ansible_host=203.0.113.10
```

Use the correct connection variables for the environment.

### Step 2 — Bootstrap SSH access

Run:

```bash
ansible-playbook playbooks/bootstrap.yml \
  -e bootstrap_host=NEW_SERVER
```

`bootstrap.yml` is specifically intended for first-time onboarding.

It uses credentials supplied through Ansible Vault and runs the `ssh_security` role to:

- create the required SSH directory
- install the official SSH public key
- configure SSH hardening
- restart SSH when configuration changes

### Step 3 — Run the main deployment

After bootstrap succeeds:

```bash
ansible-playbook playbooks/site.yml \
  --limit NEW_SERVER
```

At this point key-based SSH authentication is available and the full desired-state deployment can proceed.

---

# Why SSH Security Exists in Both Bootstrap and Site

The `ssh_security` role intentionally appears in both workflows.

### In `bootstrap.yml`

Its purpose is to establish trusted SSH access for the first time.

### In `site.yml`

Its purpose is to continuously enforce the desired SSH security policy.

This is intentional and not duplicate work.

Because the role is idempotent, a correctly configured server should normally produce `ok` instead of unnecessary changes on later runs.

This gives two guarantees:

- a fresh password-only server can be onboarded safely
- an already managed server remains compliant if SSH configuration is changed manually later

---

# Main Playbook

## `site.yml`

`site.yml` is the primary desired-state configuration entry point.

It currently applies the following stages:

1. SSH security
2. Common server configuration
3. Monitoring
4. Docker Engine
5. Application-node installation
6. Memory watchdog
7. Firewall protection for selected hosts

Run on all applicable managed hosts:

```bash
ansible-playbook playbooks/site.yml
```

Run on only one host:

```bash
ansible-playbook playbooks/site.yml \
  --limit SERVER_NAME
```

The main deployment intentionally does **not** perform full system upgrades, optimization, ICMP policy changes, or security-update policy rollout automatically.

Those operations are separated into dedicated playbooks.

---

# Other Playbooks

## `bootstrap.yml`

First-time SSH onboarding for a new server.

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

Operational tasks are intentionally separated from `site.yml`.

```text
playbooks/operations/
├── optimize.yml
├── ping-control.yml
├── security-updates.yml
└── system-update.yml
```

This separation reduces unexpected production changes during ordinary configuration runs.

## Controlled System Updates

`playbooks/operations/system-update.yml` performs controlled package maintenance.

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

`playbooks/operations/security-updates.yml` applies the `security_updates` role.

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

`playbooks/operations/optimize.yml` applies the optimization role independently.

```bash
ansible-playbook playbooks/operations/optimize.yml
```

Optimization is kept separate from ordinary provisioning so performance tuning can be executed explicitly and reviewed independently.

## ICMP / Ping Control

`playbooks/operations/ping-control.yml` manages ICMP behavior independently from the main deployment.

```bash
ansible-playbook playbooks/operations/ping-control.yml
```

This is also intentionally excluded from `site.yml`.

---

# Common Server Configuration

The `common` role handles baseline server configuration.

Current responsibilities include:

- hostname configuration
- DNS configuration
- common package installation
- runtime dependencies required by later roles

The common package list includes tools such as:

```text
btop
curl
cron
```

`cron` is installed as a baseline dependency because the watchdog role relies on the `crontab` executable.

Managing this dependency in `common` ensures newly provisioned minimal Ubuntu servers can successfully complete watchdog configuration.

---

# Monitoring

The `monitoring` role installs and starts Prometheus Node Exporter on managed hosts.

It also generates Prometheus file-service-discovery targets dynamically from the Ansible inventory.

This keeps monitoring discovery aligned with infrastructure state rather than requiring a second manually maintained server list.

## Prometheus Target Path

The generated target file is stored on the controller at:

```text
/opt/monitoring/targets/targets.json
```

The monitoring role ensures that the parent directory exists before generating the file.

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

The application role handles node installation and configuration.

The workflow includes:

- installer execution
- API configuration
- SAN/certificate configuration
- service protocol enforcement
- service restart when configuration changes
- SSL certificate retrieval to the controller

The installation task uses Ansible state checks to avoid unnecessary repeated installations.

Sensitive installer output should be handled carefully because command output can expose credentials if logging is enabled.

---

# Memory Watchdog

The `pasarguard_watchdog` role deploys a memory-watchdog script and schedules it through cron.

Because minimal servers may not include `crontab` by default, the `common` role ensures `cron` is installed before the watchdog role is reached.

This dependency was validated on fresh-server provisioning.

---

# Firewall Automation

Firewall rules are applied only to hosts in the dedicated inventory group:

```text
abuse_protected
```

If a host does not belong to that group, the firewall play is skipped.

This allows security controls to be enabled selectively without applying the same network policy to every managed node.

---

# Inventory Design

The public example inventory demonstrates functional host grouping.

Current groups include:

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
- API credentials
- domain configuration
- SSH public-key path
- external provider tokens

The public repository contains only a safe example:

```text
inventory/group_vars/all/vault.yml.example
```

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

Production Vault files and the Vault password file must not be committed.

---

# Public Repository Safety

This repository is sanitized for portfolio use.

Public files:

```text
inventory/hosts.example.ini
inventory/group_vars/all/vault.yml.example
```

Local production files are excluded through `.gitignore`.

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

Install required Ansible collections:

```bash
ansible-galaxy collection install -r requirements.yml
```

The project currently pins required collections in `requirements.yml`.

---

# Validation

## Syntax Check

```bash
ansible-playbook playbooks/site.yml --syntax-check
```

Operational playbooks can be checked individually:

```bash
ansible-playbook playbooks/operations/system-update.yml --syntax-check
ansible-playbook playbooks/operations/security-updates.yml --syntax-check
```

## Inventory Validation

```bash
ansible-inventory --graph
```

Inspect a specific host:

```bash
ansible-inventory --host SERVER_NAME
```

## Connectivity

```bash
ansible all -m ansible.builtin.ping
```

Or one host:

```bash
ansible SERVER_NAME -m ansible.builtin.ping
```

---

# Tested Fresh-Server Workflow

The following workflow has been validated against a newly provisioned password-only server:

```text
Initial site.yml attempt
    ↓
SSH public-key authentication unavailable
    ↓
bootstrap.yml
    ↓
SSH key installed
SSH hardened
    ↓
site.yml --limit NEW_SERVER
    ↓
common configuration
monitoring
Docker
application installation
watchdog
optional firewall stage
    ↓
successful deployment
```

The validated deployment confirmed:

- bootstrap access works
- SSH key installation works
- SSH hardening remains idempotent
- common packages install correctly
- `cron` is available before watchdog scheduling
- Node Exporter installs successfully
- Prometheus target generation updates correctly
- new servers appear in monitoring
- Docker installs successfully
- application provisioning completes
- watchdog scheduling completes
- group-specific firewall behavior is respected

---

# Reliability and Idempotency

The project has been validated through:

- syntax checks
- inventory validation
- connectivity checks
- fresh-server bootstrap
- full `site.yml` execution
- repeated SSH-security execution with no unnecessary changes
- monitoring target generation
- Docker provisioning
- watchdog scheduling
- controlled system upgrades
- reboot detection
- unattended security-update rollout
- selective group-based firewall execution
- real password-login rejection testing

The design goal is predictable, repeatable infrastructure management with minimal unnecessary changes on subsequent runs.

---

# Recommended New-Server Workflow

For a newly provisioned password-only server:

```bash
# 1. Add the server to inventory

# 2. Bootstrap SSH
ansible-playbook playbooks/bootstrap.yml \
  -e bootstrap_host=NEW_SERVER

# 3. Apply normal desired state
ansible-playbook playbooks/site.yml \
  --limit NEW_SERVER

# 4. Configure unattended security patching
ansible-playbook playbooks/operations/security-updates.yml \
  --limit NEW_SERVER

# 5. Apply optimization when explicitly desired
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
- controlled rolling maintenance
- automatic security patching
- reboot management
- operational playbook separation
- Git-based infrastructure workflows
- production-safe repository sanitization

---

# Roadmap

Planned improvements:

- `ansible-lint`
- `yamllint`
- GitHub Actions CI
- automated syntax validation
- secret scanning
- stronger operational timeout handling
- improved APT lock handling
- role-specific documentation
- Molecule testing
- automated idempotency testing
- additional monitoring and alerting
- supply-chain hardening for external installation scripts
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

System upgrades and optimization are not hidden inside everyday deployment.

### Reboots are controlled

Automatic security patching does not automatically reboot production nodes.

### Monitoring follows inventory

Prometheus targets are generated from Ansible inventory instead of being maintained separately.

### Host groups determine responsibility

Application deployment and firewall behavior are applied only where appropriate.

### Secrets stay out of Git

Public repository examples are sanitized and production secrets remain local and encrypted.
