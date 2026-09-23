# Ansible Infrastructure Automation

Production-oriented Ansible project for provisioning, securing, monitoring, and operating a multi-node Linux infrastructure.

The repository demonstrates a practical Infrastructure-as-Code workflow with reusable roles, secure bootstrap, Docker provisioning, monitoring, firewall automation, operational playbooks, controlled system maintenance, automatic security patching, and idempotent configuration management.

## Highlights

- Secure SSH bootstrap with key-based authentication
- Centralized inventory and group-based configuration
- Docker Engine installation from the official repository
- Prometheus Node Exporter deployment and target generation
- Application node provisioning and watchdog automation
- Abuse/firewall rule management for selected nodes
- Ansible Vault integration for sensitive configuration
- Separate operational playbooks for optimization, ICMP control, and system maintenance
- Controlled rolling system upgrades with automatic reboot detection
- Automatic security patching with unattended-upgrades and disabled automatic reboots
- Idempotent infrastructure management verified with repeated runs
- Sanitized public inventory and Vault examples for safe portfolio use

## Architecture

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
│       ├── system-update.yml
│       └── security-updates.yml
└── roles/
    ├── ssh_security/
    ├── common/
    ├── monitoring/
    ├── docker/
    ├── pasarguard/
    ├── pasarguard_watchdog/
    ├── abuse_firewall/
    ├── optimization/
    └── security_updates/
```

Production inventory and encrypted Vault files are intentionally excluded from version control. The repository contains safe example files instead.

## Playbooks

### `site.yml`

Main configuration entry point.

It applies the core infrastructure roles in order:

1. SSH security
2. Common server configuration
3. Monitoring
4. Docker
5. Application node provisioning
6. Memory watchdog
7. Firewall protection for selected nodes

```bash
ansible-playbook playbooks/site.yml
```

### `bootstrap.yml`

Used for first-time server onboarding before SSH key authentication is available.

The bootstrap workflow uses credentials supplied through Ansible Vault, installs the authorized SSH key, and applies SSH hardening to a single selected host.

```bash
ansible-playbook playbooks/bootstrap.yml -e bootstrap_host=SERVER_NAME
```

### `security.yml`

Re-applies SSH hardening independently from the full infrastructure deployment.

```bash
ansible-playbook playbooks/security.yml
```

### Operational playbooks

Operational tasks are intentionally separated from desired-state configuration:

```text
playbooks/operations/
├── optimize.yml
├── ping-control.yml
├── system-update.yml
└── security-updates.yml
```

### Controlled system updates

`system-update.yml` performs rolling package maintenance across managed nodes.

It updates the APT cache, applies distribution upgrades, removes obsolete dependencies, cleans package files, detects whether a reboot is required, and reboots only when necessary.

The playbook uses:

```yaml
serial: 1
```

This keeps maintenance sequential so only one managed node is updated or rebooted at a time.

```bash
ansible-playbook playbooks/operations/system-update.yml
```

### Automatic security updates

`security-updates.yml` applies the `security_updates` role to configure automatic security patching using Ubuntu's `unattended-upgrades`.

The configuration:

- enables periodic package-list updates
- enables unattended security updates
- limits automatic installation to security updates
- disables automatic rebooting

Reboots remain an explicit maintenance operation and can be handled safely through `system-update.yml`.

```bash
ansible-playbook playbooks/operations/security-updates.yml
```

## Inventory Design

The example inventory demonstrates functional grouping rather than provider-specific grouping.

- `pasarguard_nodes` — application nodes managed by the main deployment
- `ssh_ubuntu` — hosts accessed through an `ubuntu` user with privilege escalation
- `abuse_protected` — hosts receiving additional firewall protection

Real hostnames, IP addresses, providers, regions, and production credentials are not stored in the public repository.

## Security Model

SSH access is hardened to use public-key authentication.

The role enforces settings such as:

```text
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
```

Secrets and environment-specific values are referenced through Ansible Vault. Production Vault files, Vault passwords, private keys, real domains, and real inventory data are excluded from Git.

## Monitoring

The monitoring role installs and enables Prometheus Node Exporter and generates Prometheus targets dynamically from the Ansible inventory.

This keeps monitoring discovery aligned with infrastructure state instead of maintaining a separate static target list.

## Docker Provisioning

The Docker role:

- installs required dependencies
- configures the official Docker repository
- installs Docker Engine, Buildx, and the Compose plugin
- enables and starts the Docker service

## Reliability and Idempotency

The infrastructure was validated with:

- Ansible syntax checks
- connectivity checks across managed nodes
- full `site.yml` execution
- repeated execution with `changed=0`
- rolling package upgrades with reboot detection
- unattended security-update deployment across managed nodes
- SSH effective-configuration checks
- real password-login rejection tests

The goal is predictable, repeatable infrastructure management without unnecessary changes on subsequent runs.

## Public Repository Safety

This repository is sanitized for portfolio use.

Use the example files as templates:

```text
inventory/hosts.example.ini
inventory/group_vars/all/vault.yml.example
```

Create local production copies when deploying:

```bash
cp inventory/hosts.example.ini inventory/hosts.ini
cp inventory/group_vars/all/vault.yml.example inventory/group_vars/all/vault.yml
```

Then encrypt the production Vault file:

```bash
ansible-vault encrypt inventory/group_vars/all/vault.yml
```

Do not commit production inventory, Vault passwords, private SSH keys, real domains, or infrastructure credentials.

## Dependencies

Install the required Ansible collections:

```bash
ansible-galaxy collection install -r requirements.yml
```

## Validation

Syntax check:

```bash
ansible-playbook playbooks/site.yml --syntax-check
```

Inventory validation:

```bash
ansible-inventory --graph
```

Connectivity:

```bash
ansible all -m ansible.builtin.ping
```

## Skills Demonstrated

This project demonstrates hands-on experience with:

- Ansible and Infrastructure as Code
- Linux server provisioning
- SSH hardening and privilege escalation
- Secrets management with Ansible Vault
- Docker deployment
- Prometheus monitoring
- Firewall automation
- Linux package lifecycle and security patch management
- Controlled rolling maintenance and reboot handling
- Idempotent configuration management
- Multi-node infrastructure operations
- Git-based infrastructure workflows

## Roadmap

Planned improvements:

- `ansible-lint` and `yamllint`
- GitHub Actions CI for automated validation
- additional test automation
- further role documentation
