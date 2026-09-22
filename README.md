# PasarGuard Ansible Infrastructure

Ansible infrastructure project for provisioning, securing, configuring, and operating PasarGuard nodes.

## Project Structure

```text
ansible-project/
├── ansible.cfg
├── requirements.yml
├── inventory/
│   ├── hosts.ini
│   └── group_vars/
│       ├── all/
│       │   ├── vars.yml
│       │   └── vault.yml
│       └── ssh_ubuntu.yml
├── playbooks/
│   ├── bootstrap.yml
│   ├── security.yml
│   ├── site.yml
│   └── operations/
│       ├── optimize.yml
│       └── ping-control.yml
└── roles/
    ├── ssh_security/
    ├── common/
    ├── monitoring/
    ├── docker/
    ├── pasarguard/
    ├── pasarguard_watchdog/
    ├── abuse_firewall/
    └── optimization/
```

## Main Playbooks

### `site.yml`

Main configuration playbook.

It applies:

1. SSH security
2. Common server configuration
3. Prometheus Node Exporter monitoring
4. Docker Engine
5. PasarGuard
6. PasarGuard memory watchdog
7. Abuse-Defender firewall rules on selected nodes

Run:

```bash
ansible-playbook playbooks/site.yml
```

### `bootstrap.yml`

Used only for initial provisioning of a new server before SSH key authentication has been established.

The bootstrap process uses credentials stored in Ansible Vault, installs the authorized SSH key, and applies SSH security configuration.

Run for a single host:

```bash
ansible-playbook playbooks/bootstrap.yml \
  -e bootstrap_host=SERVER_NAME
```

After bootstrap, normal Ansible management uses SSH key authentication.

### `security.yml`

Applies SSH security configuration independently:

```bash
ansible-playbook playbooks/security.yml
```

### Operations

Operational playbooks are kept separately under:

```text
playbooks/operations/
```

They include:

- `optimize.yml` — server optimization
- `ping-control.yml` — connectivity/control operations

## Inventory Groups

### `pasarguard_nodes`

Servers managed as PasarGuard nodes.

### `ssh_ubuntu`

Servers where Ansible connects using the `ubuntu` user and uses passwordless sudo for privilege escalation.

### `abuse_protected`

Servers where Abuse-Defender firewall rules are applied.

## SSH Security

Managed servers are configured for key-based SSH authentication.

Expected effective SSH configuration:

```text
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
```

Some OpenSSH versions may report:

```text
PermitRootLogin without-password
```

which provides the same password-login restriction for root.

## Monitoring

Prometheus Node Exporter is installed and enabled on managed hosts.

Default exporter port:

```text
9100
```

Prometheus targets are generated from the Ansible inventory at:

```text
/opt/monitoring/targets.json
```

## Secrets

Sensitive values are stored with Ansible Vault.

The project references secrets such as:

```text
vault_ansible_password
vault_ansible_become_pass
vault_cf_api_token
vault_common_api_key
```

Do not store plaintext secrets, private SSH keys, or Vault passwords in the repository.

## Dependencies

Install required Ansible collections with:

```bash
ansible-galaxy collection install -r requirements.yml
```

## New Server Workflow

1. Add the server to `inventory/hosts.ini`.
2. Assign it to the appropriate inventory groups.
3. Ensure the initial credentials required for bootstrap are available through Ansible Vault.
4. Run `bootstrap.yml` for that host.
5. Verify SSH key connectivity.
6. Run `site.yml` for that host.
7. Verify the resulting services and security configuration.

Example:

```bash
ansible-playbook playbooks/bootstrap.yml \
  -e bootstrap_host=NEW-SERVER

ansible NEW-SERVER -m ansible.builtin.ping

ansible-playbook playbooks/site.yml \
  --limit NEW-SERVER
```

## Validation

Syntax check:

```bash
ansible-playbook playbooks/site.yml --syntax-check
```

Connectivity:

```bash
ansible all -m ansible.builtin.ping
```

A repeat execution of `site.yml` should normally complete without failures or unreachable hosts and should produce no configuration changes when the infrastructure is already in the desired state.
