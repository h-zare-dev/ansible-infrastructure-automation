# Ansible Infrastructure Automation

Production-oriented Ansible project for provisioning, securing, monitoring, and operating a multi-node Linux infrastructure.

This repository uses focused Ansible roles for SSH access, DNS and baseline Linux setup, pinned operational tooling, Docker, Prometheus monitoring, PasarGuard nodes, watchdog automation, firewall controls, Port Forward Manager installation, native network tuning, and controlled maintenance.

The project is designed around two distinct workflows:

1. **Initial server onboarding** — update the host, install baseline operational tooling, establish SSH access, create a Cloudflare DNS record, and update controller SSH shortcuts.
2. **Ongoing desired-state management** — repeatedly apply configuration safely and idempotently.

Ongoing fleet system upgrades, security-update policy, ICMP control, and optimization remain explicit operational actions. Bootstrap is the intentional exception for system updates: it runs `system_update` once during onboarding with reboot-on-required enabled.

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
- Independent operational playbooks for system updates, security updates, ping control, Port Forward Manager, and native network optimization
- Pinned Ookla Speedtest CLI installation on supported hosts
- Pinned `floatip-manager` installation on detected Hetzner hosts
- Dedicated `port_forward_nodes` group for pinned native nftables v2 forwarding, DNS refresh service/timer installation, and legacy-safe coexistence
- RAM-aware, non-regressive BBR/conntrack/TCP tuning with Ansible check-mode support
- Ansible Vault integration for secrets and environment-specific values
- Public repository sanitization for safe portfolio use
- GitHub Actions CI with pinned validation tooling and sanitized example inventory

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
│       ├── port-forward-manager.yml
│       ├── security-updates.yml
│       └── system-update.yml
├── .github/workflows/
│   ├── ci.yml
│   └── release.yml
├── CHANGELOG.md
├── molecule/
│   ├── core_roles/
│   └── release_system/
├── scripts/
│   ├── extract-release-notes.py
│   ├── full-release-qualification.sh
│   └── validate.sh
├── tests/
│   └── release/
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
    ├── port_forward_manager/
    ├── security_updates/
    ├── speedtest_cli/
    ├── ssh_security/
    └── system_update/
```

Production inventory, Vault data, Vault password files, private keys, and credentials are excluded from version control.

---

## Port Forward Manager host group — native nftables v2

The optional `port_forward_nodes` inventory group installs the native
**nftables** engine from the independent
[`iptables-forward-manager`](https://github.com/h-zare-dev/iptables-forward-manager)
repository. The upstream repository name is historical; **Ansible does not
install the legacy iptables engine** on fresh hosts.

At each playbook run, the controller queries GitHub's latest published,
stable Release and downloads artifacts from that release tag. Thus new releases
do **not** require edits to Ansible variables, commits, or PRs. GitHub must
be reachable from the controller to resolve the tag. The tag selected for a
single playbook execution is consistent across all forwarding hosts.
The role downloads exactly these native manager artifacts, without
executing either upstream installer:

- `/usr/local/bin/portfw-nft` — native nftables v2 CLI (version selected from latest stable GitHub Release)
- `/etc/systemd/system/portfw-nft.service` — boot-time rule restoration
- `/etc/systemd/system/portfw-dns-refresh.service` — DNS destination refresh
- `/etc/systemd/system/portfw-dns-refresh.timer` — configurable refresh schedule

The role also installs minimal system packages including `python3`,
`nftables`, `iproute2`, `util-linux`, and `libc-bin`. It does **not**
download the legacy `portfw` CLI, install
`iptables-forward-manager.service`, or install `portfw-migrate`.
The state directory remains named `/etc/iptables-forward-manager` for
upstream compatibility; the directory name **does not mean that legacy
iptables forwarding is being installed**.

Add desired hosts to your private `inventory/hosts.ini` (never commit
production inventory):

```ini
[port_forward_nodes]
forward-de01
forward-tr01
```

The role is included in the third play of `playbooks/site.yml` for group
members. For an isolated install/update without running other roles, use:

```bash
# Entire forwarding group
ansible-playbook playbooks/operations/port-forward-manager.yml

# One member of the group
ansible-playbook playbooks/operations/port-forward-manager.yml --limit Test-DE
```

**Installation and updates do not activate forwarding.** Ansible fetches the latest stable release on every run, creates
`rules.db` only if absent, preserves existing rules and state, installs
the CLI and units, and reloads systemd unit definitions. It does not
start/stop/enable/disable the forwarding service or DNS timer, and does
not apply, reload, or remove any live NAT rules. As a consequence,
pre-existing enabled/active service states are *preserved*, not reset.

**Fresh servers:** only the native manager is installed. After you add a
forwarding rule with `sudo portfw-nft`, the upstream CLI applies that rule
and enables `portfw-nft.service` for boot restoration. It does **not** automatically start the oneshot unit. In v2.1.0, adding or editing a domain rule can automatically enable the DNS scheduler; this is upstream CLI behavior, not an Ansible action. Consequently,
the native service may show `enabled / inactive` while the managed
`ip ifm_portfw` table and forwarding rules are already present in the
kernel. This is not, by itself, an error; `enabled` describes future
boot activation rather than current service activity. A successful
post-reboot restore and end-to-end forwarding require separate testing.

**Existing legacy servers:** Ansible installs the same native files
**side by side** and does not touch the old `portfw` executable,
`iptables-forward-manager.service`, or active legacy rules. It does
not perform or install migration. Because both implementations share
`rules.db` and can conflict in NAT hooks, **do not activate or apply
native forwarding on a legacy-active server** without a separately planned
and validated cutover. The role also does not uninstall either engine when
a host is removed from `port_forward_nodes`.

### Destination DNS refresh

Adding a native rule with a domain destination resolves IPv4 A records
at the time of addition. In v2.1.0, the native Add/Edit workflow provides
per-rule DNS refresh and optional Timed Rotation or Per-Connection Round Robin;
it can automatically enable the shared scheduler for domain rules.
Ansible installs the DNS refresh service/timer but never activates them
itself. For older rules or explicit scheduler administration, the CLI can
inspect or configure the timer:

```bash
sudo portfw-nft timer --minutes 5 --enable

# Read-only service and timer checks
systemctl is-enabled portfw-dns-refresh.timer || true
systemctl is-active portfw-dns-refresh.timer || true
journalctl -u portfw-dns-refresh.service --since "1 hour ago" --no-pager

# Opt out later
sudo portfw-nft timer --disable
```

Supported intervals are 1, 2, 3, 5, 10, 15, 20, 30, 45, and 60
minutes. A normal `DNS: unchanged; firewall untouched` log entry
indicates a successful check without any required map update; it does
not prove behavior under a real DNS address change. On a host still
forwarding only through legacy iptables, leave native DNS refresh
disabled until the cutover has been verified.

### Verifying Ansible installation and idempotency

```bash
ansible-playbook playbooks/operations/port-forward-manager.yml --limit Test-DE
ansible-playbook playbooks/operations/port-forward-manager.yml --limit Test-DE
```

The second run should report `changed=0` if the latest Release, files, and packages
remain unchanged. When a new stable Release is published, the next normal
`site.yml` or standalone port-forward-manager playbook run downloads its
native artifacts on all targeted hosts. This upgrades the files **without**
restarting running units, reapplying kernel rules, or guaranteeing that the
new binary has taken effect for an already active service/timer. Check
release notes before invoking the playbook on production. On the managed host, `portfw-nft --version`,
`portfw-nft check`, and `portfw-nft list` are safe basic checks.
`nft list table ip ifm_portfw` shows whether native rules currently
exist in the kernel. These checks do not, by themselves, prove
end-to-end TCP/UDP connectivity, successful DNS address rotation, or
boot-time restoration. Avoid `portfw-nft apply`, `reload`, or
service restarts merely to verify a live legacy installation.

Port Forward Manager remains independent of `floatip-manager`.

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
      → controller_known_hosts (empty ALL controller-user known_hosts fingerprints)
      → ssh_security
      → cloudflare_dns
      → controller_ssh_config
      → flush pending SSH handlers
      → reset SSH connection and verify reconnect
      → system_update (FINAL; reboot when required)
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

`bootstrap.yml` targets `bootstrap_host`. Its first play disables fact gathering and runs `controller_known_hosts` entirely on localhost, before any SSH connection to the server. **Every bootstrap clears the complete contents** of `controller_known_hosts_path` (by default the Ansible controller process user's `~/.ssh/known_hosts`) with mode `0600`. This includes all hostnames, IPs, ports and hashed entries, including fingerprints for unrelated servers. If the file does not exist, the role creates an empty file and the private `~/.ssh` directory as necessary. It does not delete the controller's SSH config, private keys, or any server's authorized keys.

**Security tradeoff:** Emptying `known_hosts` discards prior host-key trust for *every* connection made by that controller user. Verify newly presented server host-key fingerprints through an independent trusted channel before accepting them. The `ansible.cfg` currently disables Ansible's `host_key_checking`, which further reduces its ability to detect impersonation; this reset does not restore that protection. Running Ansible as root resets `/root/.ssh/known_hosts`, not `/home/hossein/.ssh/known_hosts`. Use an explicit `controller_known_hosts_path` only if a different controller-user file is intended.

The remote bootstrap play uses Vault-provided SSH and privilege-escalation passwords. Its role order is `ssh_security`, `cloudflare_dns`, `controller_ssh_config`, then a flush of pending SSH handlers, an SSH reconnect check, and as the final task, `system_update`:

- `ssh_security` installs managed SSH public keys, deploys SSH hardening and notifies a service-restart handler on changes.
- `cloudflare_dns` creates or updates the host's Cloudflare A record.
- `controller_ssh_config` updates all inventory SSH shortcuts on the controller.
- **Before the final update:** Ansible flushes pending SSH hardening handlers, resets its SSH session and verifies that it can reconnect. This prevents starting a rebooting OS upgrade when hardened SSH access has become unusable.
- **Last:** `system_update` performs the OS package upgrade and optional reboot, after a BIOS GRUB preflight. If the final step fails, earlier bootstrap actions may already have succeeded, but the play remains failed.

**GRUB safety:** Debian-family systems using BIOS + `grub-pc` are inspected **read-only** before APT changes. Existing valid whole-disk GRUB selections are preserved. An absent or stale target is repaired via Debconf only if the firmware boot disk selection is unambiguous (single disk with a compatible partition layout). UEFI and non-`grub-pc` hosts are left untouched. Multi-disk, unknown or unsupported arrangements fail safely before the upgrade. The role never calls `grub-install` directly or answers "Continue without installing GRUB?" with Yes. Subsequent APT package scripts may install GRUB on the selected disk, so ensure backup and provider recovery console access before upgrading.

`system_update_grub_preflight_enabled` defaults to `true`. Turning it off bypasses preflight, but does not solve GRUB prompts.

**Avoiding duplicate first-run utility installs:** Bootstrap intentionally does not install `speedtest_cli` or `floatip_manager`. Both remain in the all-host play of `site.yml` and install only when relevant. `ssh_security`, `cloudflare_dns` and `controller_ssh_config` run in both workflows on purpose: Bootstrap establishes first access and DNS, while later Site runs reconcile security keys, host records and inventory aliases if they drift. No separate TLS/SSL certificate role exists in either workflow.

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

`site.yml` is the primary desired-state configuration entry point. It has three logical plays with separate, single-responsibility roles:

1. **All managed servers** — gathers facts once, then runs `ssh_security`, `controller_ssh_config`, `cloudflare_dns`, `hostname`, `dns_resolver`, `base_packages`, `speedtest_cli`, `floatip_manager`, and `monitoring` in that order. `floatip_manager` is conditional on Hetzner detection. Controller SSH shortcuts and monitoring targets are generated on the controller.
2. **`pasarguard_nodes`** — sets `gather_facts: false` and runs `docker`, `pasarguard`, and `pasarguard_watchdog`, followed by `abuse_firewall` only for hosts also in `abuse_protected`.
3. **`port_forward_nodes`** — gathers facts and runs only `port_forward_manager` on group members. It installs and enables the forwarding tool but does not apply forwarding rules.

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

Initial SSH, Cloudflare DNS and controller shortcut onboarding for a new or rebuilt server. Bootstrap empties the controller-user known_hosts file, establishes managed SSH/DNS/controller access, then performs the system update **last** (including a reboot when required). Ookla Speedtest and FloatIP Manager installation are deferred to `site.yml`; `site.yml` does not run the host-key cleanup or the system-update operation.

```bash
ansible-playbook playbooks/bootstrap.yml \
  -e bootstrap_host=SERVER_NAME
```

Use this before `site.yml` when the server does not yet accept the managed SSH key.

## `security.yml`

Re-applies SSH hardening independently from the full deployment to all inventory hosts by default.

```bash
ansible-playbook playbooks/security.yml

# Target one inventory host
ansible-playbook playbooks/security.yml --limit SERVER_NAME
```

Useful when SSH policy needs to be enforced without running unrelated roles.

---

# Playbook Quick Reference

All eight tracked playbooks and their invocation contracts are summarized below. Host names in examples are inventory aliases, not DNS names.

| Playbook | Target | Purpose | Important input |
| --- | --- | --- | --- |
| `playbooks/bootstrap.yml` | `bootstrap_host` | First-time onboarding; may reboot | **Required** `-e bootstrap_host=SERVER_NAME` |
| `playbooks/site.yml` | `all`, `pasarguard_nodes`, `port_forward_nodes` | Reconcile the normal desired state | Optional `--limit SERVER_NAME` |
| `playbooks/security.yml` | `all` | Reapply SSH hardening | Optional `--limit SERVER_NAME` |
| `playbooks/operations/system-update.yml` | `all` | Rolling full package upgrade, reboot if required | Optional `--limit SERVER_NAME` |
| `playbooks/operations/security-updates.yml` | `all` | Configure unattended security updates | Optional `--limit SERVER_NAME` |
| `playbooks/operations/optimize.yml` | `common` by default | Explicit host network optimization | `-e optimize_hosts=GROUP_OR_HOST`; check-mode `--check --diff` |
| `playbooks/operations/ping-control.yml` | `all` | Control IPv4 Ping replies | **Explicitly specify** `-e ping_action=block` or `allow` |
| `playbooks/operations/port-forward-manager.yml` | `port_forward_nodes` | Install/maintain forwarding utility only | Optional `--limit SERVER_NAME` |

`--limit` narrows the eligible play hosts; it never adds a host to a group it is not already in. In particular, `--limit SERVER_NAME` cannot make a host outside `port_forward_nodes` eligible for the standalone forwarding play. Production inventory remains private.

---

# Operational Playbooks

System upgrades, security-update policy, ping control, optimization, and targeted Port Forward Manager maintenance have standalone operational entry points. Port Forward Manager is also installed by `site.yml` for members of its group.

```text
playbooks/operations/
├── optimize.yml
├── ping-control.yml
├── port-forward-manager.yml
├── security-updates.yml
└── system-update.yml
```

Keeping these operations separate avoids adding them to ordinary configuration runs.

## Port Forward Manager — Standalone Installation and Maintenance

`playbooks/operations/port-forward-manager.yml` targets `port_forward_nodes` and runs only the existing `port_forward_manager` role, without the unrelated roles from `site.yml`.

```bash
# All forwarding hosts
ansible-playbook playbooks/operations/port-forward-manager.yml

# A single forwarding host (must belong to port_forward_nodes)
ansible-playbook playbooks/operations/port-forward-manager.yml --limit Test-DE
```

It installs the pinned native `portfw-nft` CLI, its rule-restore service, and its DNS refresh service/timer. Existing `rules.db`, legacy CLI/service and live forwarding are preserved. Ansible never installs migration tooling or legacy executables and never changes activation state or applies/reloads rules. The upstream native CLI enables boot persistence after the first successful Add; starting with v2.1.0, domain Add/Edit can also enable its DNS scheduler automatically.

Removing a host from the group does not uninstall the tool or remove existing rules. For the group definition and use of `portfw-nft`, see [Port Forward Manager host group](#port-forward-manager-host-group--native-nftables-v2).

## Controlled System Updates

`playbooks/operations/system-update.yml` performs controlled package maintenance on all inventory hosts (`all`). The underlying `system_update` role supports Debian-family and RedHat-family hosts.

On Debian-family hosts it refreshes APT metadata, performs a distribution upgrade, removes unused dependencies, cleans obsolete package files, and checks `/var/run/reboot-required`. On RedHat-family hosts it updates installed packages through `dnf` and uses `needs-restarting -r` when available to determine reboot need. In both cases the operational playbook reboots only when the role reports that a reboot is required.

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

This playbook is intentionally **not** part of `site.yml`. All inventory hosts are eligible; the separate `--limit` option can narrow that set. It performs a rolling update (`serial: 1`) and may reboot a host when required.

## Automatic Security Updates

`playbooks/operations/security-updates.yml` applies the `security_updates` role to all inventory hosts (`all`), one host at a time.

It configures Debian-family hosts for automatic security patching using `unattended-upgrades` and manages `needrestart` explicitly.

The role:

- installs `unattended-upgrades`, `apt-listchanges`, and `needrestart`
- enables periodic package-list refreshes
- enables unattended security updates
- limits automatic installation to security updates
- disables automatic rebooting by default
- keeps `needrestart` in automatic mode for ordinary services by default
- prevents `systemd-networkd.service`, `networking.service`, and `NetworkManager.service` from being restarted automatically
- supports `security_updates_needrestart_mode: "l"` when every service restart should be deferred to a maintenance window

Ubuntu 24.04 and later can automatically restart affected services after APT transactions. The network-service exclusions are intentional: restarting the active network manager can interrupt connectivity and can remove runtime-only secondary or floating addresses until their persistent configuration is reapplied.

The default policy therefore keeps security packages installing automatically while deferring critical network-manager restarts. Other affected services can still be restarted automatically so patched libraries take effect promptly.

Automatic reboot remains disabled. Reboots and any deferred critical-service restarts are controlled maintenance actions and can be coordinated with `system-update.yml`.

Run on one canary first:

```bash
ansible-playbook playbooks/operations/security-updates.yml \
  --limit SERVER_NAME
```

Then roll out to the fleet:

```bash
ansible-playbook playbooks/operations/security-updates.yml
```

This playbook is intentionally separate from `site.yml`. It targets every inventory host (`all`) and configures unattended security updates on Debian-family hosts; non-Debian hosts fail the role's platform assertion. Automatic reboot remains disabled.

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

`playbooks/operations/ping-control.yml` manages **IPv4 ICMP Echo Request (Ping) replies** on inventory hosts. This operation is independent of `site.yml` and does not disable SSH or all ICMP traffic.

**Block Ping on all inventory hosts:**

```bash
ansible-playbook playbooks/operations/ping-control.yml \
  -e "ping_action=block"
```

**Allow Ping again on all inventory hosts:**

```bash
ansible-playbook playbooks/operations/ping-control.yml \
  -e "ping_action=allow"
```

**Block Ping on one host only** (use its exact inventory name):

```bash
ansible-playbook playbooks/operations/ping-control.yml \
  --limit Test-DE \
  -e "ping_action=block"
```

**Verify the current setting on all hosts:**

```bash
ansible all -b -m ansible.builtin.command \
  -a "sysctl net.ipv4.icmp_echo_ignore_all"
```

A value of `1` means IPv4 Echo replies are disabled; `0` means they are enabled at the kernel setting. External Ping can also be blocked by other firewall/network rules. The playbook uses `ansible.posix.sysctl` with persistent configuration, so its setting survives reboots.

**Important:** The default `ping_action` is `allow`. Running the playbook **without** `-e "ping_action=block"` allows IPv4 Ping replies. Always specify the desired action explicitly when performing operational maintenance.

This playbook is intentionally excluded from `site.yml`.

---

# Role Responsibilities

The former `common` role was split into focused responsibilities. Current roles are:

| Role | Responsibility |
| --- | --- |
| `ssh_security` | Install the managed SSH public key and enforce server SSH policy. |
| `controller_known_hosts` | Clear the entire controller user's `known_hosts` file before initial connection (all stored fingerprints). |
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
- `port_forward_nodes` — hosts receiving the independent native nftables Port Forward Manager installer; a host may also belong to other functional groups

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

# GitHub Release and Versioning

The repository has a curated `CHANGELOG.md` and a manual publication workflow in `.github/workflows/release.yml`. Releases are **not** deployments to production hosts.

To publish a subsequent version after the current `v1.1.0`, first update `CHANGELOG.md` with a matching header such as `## [1.1.1] - YYYY-MM-DD`, review/merge the change through `development`, and promote it to `main` after Full Release Qualification succeeds. Then, in GitHub **Actions → Release → Run workflow**, select **main** and provide the version (for example `v1.1.1`). The workflow extracts that changelog entry, checks for an existing release, and creates the tag and release from `main`.

Do not rerun publication for an existing tag/version expecting to overwrite it, and do not run it from `development`. Published tags such as `v1.0.0` and `v1.1.0` remain fixed even when newer changes reach `main`. The nftables-only installer was merged after `v1.1.0`; it does not retroactively change that release.

---

# CI and Validation

GitHub Actions is the authoritative validation environment for pull requests and protected branches. The Ansible controller does not need Python development packages, `ansible-lint`, `yamllint`, or Galaxy validation dependencies installed merely to validate repository changes.

The workflow is defined in:

```text
.github/workflows/ci.yml
```

It runs for pull requests targeting `development` or `main`, for pushes to those protected branches, and by manual workflow dispatch.

The CI workflow has a stable final status named `CI Gate`.

1. **Repository Validation**
   - checks out the full repository history without persisting GitHub credentials
   - uses Ubuntu 24.04 with Python 3.13
   - installs the exact versions pinned in `requirements-dev.txt`
   - installs the exact Ansible collections pinned in `requirements.yml`
   - runs `./scripts/validate.sh`
   - validates the sanitized example inventory structure
   - renders and syntax-checks the managed `needrestart` configuration
2. **Molecule Integration**
   - creates disposable Docker targets for Ubuntu 24.04 and Ubuntu 26.04
   - applies the CI-safe `base_packages` and `security_updates` roles
   - reruns convergence and fails if the second run changes state
   - verifies installed packages and generated security-update configuration
   - destroys the test containers after the scenario
3. **Full Release Qualification**
   - runs on `development`, `main`, and pull requests targeting `main`
   - uses disposable privileged systemd containers for Ubuntu 24.04 and Ubuntu 26.04
   - exercises controller-side SSH configuration and known-host cleanup against sandbox files
   - exercises hostname, resolver, SSH hardening, monitoring, FloatIP installer, native nftables Port Forward Manager installer and DNS refresh units (fixture-based, no rule apply), Speedtest installer, PasarGuard with a mock installer, watchdog, Abuse Firewall, and Debian system-update behavior
   - runs Molecule idempotency across the release-system scenario
   - contract-tests Cloudflare, Docker, FloatIP separation, optimization non-goals, and branch/playbook topology without contacting provider APIs
   - exercises optimization tier/capacity calculations with synthetic host facts
   - renders optimization, firewall, and watchdog artifacts and validates them with Bash syntax checks, ShellCheck, and `systemd-analyze verify`

For normal feature/fix PRs targeting `development`, Full Release Qualification is skipped to keep feedback fast. It becomes mandatory on the protected promotion path to `main`. The final `CI Gate` fails whenever a mandatory release qualification run does not succeed.

The Python validation and integration-test toolchain is pinned for reproducibility:

```text
ansible-core==2.21.5
ansible-lint==26.9.0
yamllint==1.38.0
molecule==26.9.0
molecule-plugins[docker]==26.7.15
docker==7.2.0
```

The Galaxy collections are also version-pinned in `requirements.yml`, including `community.docker` for the Molecule Docker driver.

`scripts/validate.sh` checks PR diff formatting, YAML lint, Ansible lint, syntax-checks every playbook using an isolated copy of the sanitized example inventory, verifies required operational playbooks, and rejects accidentally tracked production inventory, Vault data, private-key-style filenames, and private-key material.

CI uses no production SSH keys, Vault passwords, Cloudflare tokens, or production inventory and does not contact production hosts. Molecule and Full Release Qualification operate only on disposable containers, generated fixtures, and sandbox controller paths inside the GitHub-hosted runner.

Local validation remains available only as an optional developer convenience. If desired, create a disposable local virtual environment and install the same pinned dependencies, but local validation is not required before opening or merging a PR.

A few existing task-specific ansible-lint findings remain narrowly ignored to preserve production behavior. The existing Docker `apt_repository` deprecation warning remains outside this CI phase.

Production connectivity, deployment, application behavior, and reboot/network verification remain manual operator responsibilities after the repository CI gate passes.

---

# Reliability and Idempotency

Repeated runs should normally report `ok` for already-correct SSH security, Cloudflare DNS records, hostname, resolver settings, baseline packages, controller SSH shortcuts, and monitoring target generation. Ubuntu SSH-user detection is safe in Ansible check mode. GitHub Actions enforces Molecule idempotency for `base_packages` and `security_updates`, and Full Release Qualification expands idempotency coverage across the release-system scenario on disposable Ubuntu 24.04 and 26.04 containers.

The native `optimization` operation is also designed for idempotent normal runs and supports `--check --diff`. A first migration run can legitimately report changes while it installs repository-owned tuning files and retires old ServerTools artifacts; once converged, repeated normal runs should report no changes unless the host state or desired variables changed. Local linting and syntax checks validate repository structure; the operator must still verify actual access, DNS, monitoring, networking, and reboot behavior in the production environment.

---

# Recommended New-Server Workflow

For a newly provisioned password-only server:

```bash
# 1. Add the server to inventory

# 2. Bootstrap SSH/DNS access, then update the OS LAST
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
- Molecule integration testing on Ubuntu 24.04 and 26.04
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

- secret scanning
- stronger operational timeout handling
- improved APT lock handling
- role-specific documentation
- expand isolated coverage for provider-backed roles without introducing production credentials
- additional monitoring and alerting
- checksum/signature validation for externally downloaded operational artifacts
- automate future patch/minor release review and changelog maintenance
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