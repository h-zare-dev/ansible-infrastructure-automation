# Native Network Host Optimization

`playbooks/operations/optimize.yml` applies the repository-owned `optimization`
role. The role no longer downloads or executes ServerTools or any other remote
optimization script.

The filename of this document is retained for repository history, but the
current role is deliberately generic: its default profile is `network-host`
and its default play target is the `common` inventory group.

## Execution model

Normal run:

```bash
ansible-playbook playbooks/operations/optimize.yml
```

Safe preview:

```bash
ansible-playbook playbooks/operations/optimize.yml --check --diff
```

Override the play target when a canary is outside `common`:

```bash
ansible-playbook playbooks/operations/optimize.yml \
  -e optimize_hosts=Test-DE
```

`--limit` can still narrow the selected play hosts, but it does not replace the
play's host pattern. Use `optimize_hosts` when the target is not a member of
`common`.

## What the role manages

The role owns host-level performance settings only:

- BBR when supported by the running kernel, with supported congestion-control
  and qdisc fallback selection.
- RAM-aware accept queues, socket-buffer ceilings, and conntrack capacity.
- Optional user-count-aware conntrack sizing through
  `optimization_expected_users`.
- Non-regressive scalar and TCP-buffer sizing: already-higher live kernel values
  are preserved instead of being reduced.
- External TCP listener reservation inside the ephemeral port range while
  preserving existing reserved ranges.
- TCP path settings, keepalive/timeout policy, PMTU black-hole probing, and
  loose reverse-path filtering suitable for VPS, tunnel, and floating-IP
  environments.
- File-descriptor limits for PAM and systemd without restarting Docker or
  application containers.
- RPS/RFS/XPS for under-queued NICs through a generated oneshot systemd service.
- Optional CPU governor and THP modes; both preserve the current host state by
  default.
- Adaptive swappiness based on the already-existing swap backend. The role does
  not create or remove swap.
- Journald disk caps and systemd NTP enablement when available.
- Safe retirement of conflicting files left by the former ServerTools
  integration.

The installed sysctl/module/performance file names still contain the historical
`vpn-network` prefix. They were intentionally retained during migration to
avoid unnecessary file-path churn and service migration side effects.

## Capacity tiers

The role selects a tier from total RAM and never lowers an already-higher live
capacity value.

| Tier | RAM | somaxconn | netdev backlog | buffer ceiling | conntrack target |
| --- | ---: | ---: | ---: | ---: | ---: |
| S | <= 1.5 GB | 8,192 | 16,384 | 8 MiB | 65,536 |
| M | <= 6 GB | 16,384 | 32,768 | 16 MiB | 262,144 |
| L | <= 24 GB | 32,768 | 65,536 | 32 MiB | 1,048,576 |
| XL | > 24 GB | 65,535 | 65,536 | 64 MiB | 2,097,152 |

When `optimization_expected_users > 0`, the role calculates conntrack demand
from the expected online-user count, clamps it to a bounded range, estimates
conntrack/proxy memory pressure, and warns when the requested capacity is too
aggressive for available RAM. Buffer ceilings remain RAM-tier based.

## Defaults

Important role defaults include:

```yaml
optimization_profile: "network-host"
optimization_expected_users: 0
optimization_live_qdisc_replace: false
optimization_manage_limits: true
optimization_manage_perf: true
optimization_manage_journald: true
optimization_manage_ntp: true
optimization_rps_mode: "auto"
optimization_cpu_governor: "preserve"
optimization_thp_mode: "preserve"
optimization_nofile_limit: 1048576
```

## Safety verification

The preflight captures the host's networking identity and relevant runtime state
before tuning. Final verification checks:

- critical live sysctl values
- default IPv4 route
- canonical IPv4 address set on the default interface
- resolver-file checksum
- active root qdisc
- running Docker container IDs
- post-run Ansible reachability

The role fails if it unexpectedly changes the route, interface IPv4 addresses,
resolver, live qdisc (unless live replacement was explicitly enabled), or the
set of running Docker containers.

The final report also shows profile/tier, selected congestion control and qdisc,
buffer and conntrack values, reserved ports, network-counter deltas, and an
explicit reminder that DNS, MTU, firewall policy, and Docker restarts were not
managed.

## Check mode

The role supports Ansible `--check` mode without turning the preview into a
fake normal run:

- read-only runtime probes execute so the plan is based on the real host state
- kernel-module checks use dry-run probing instead of loading modules
- BBR/qdisc capability can be predicted when modules are available but not yet
  loaded
- mutating Ansible tasks remain native check-mode predictions
- exact desired-value assertions are enforced in normal mode, while check mode
  still validates that the live keys can be read
- the conntrack-bucket writability probe is skipped because the kernel exposes
  writability only through a write-style test

A check-mode run can therefore predict a legitimate change without modifying
the server.

## Deliberately not managed

The optimization role does not own:

- DNS resolver configuration
- interface MTU or Netplan/networkd addressing
- UFW or firewall policy
- IPv6 disablement
- Docker daemon restarts
- application/container restarts
- swap creation or removal
- `tcp_tw_reuse`, `tcp_fastopen`, `tcp_no_metrics_save`, SACK, timestamps,
  fixed UDP memory pools, or NIC ring resizing
- live root-qdisc replacement unless
  `optimization_live_qdisc_replace=true` is explicitly supplied

Some of these responsibilities exist elsewhere in the repository (for example
DNS and firewall policy); others are intentionally excluded because they are
higher-risk or workload-specific.

## ServerTools migration

The role verifies the new tuning before it removes known conflicting
ServerTools-managed files. It then flushes the relevant handlers and verifies
the final state again. This ordering prevents the migration cleanup from being
treated as successful before the replacement tuning is active.

The migration removes only the known ServerTools sysctl/module/performance,
limits, and journald artifacts that conflict with the native role.

## Recommended canary validation

1. Run `--check --diff` and review predicted changes.
2. Record a Speedtest result if throughput comparison is useful.
3. Run the normal play on one canary.
4. Review the optimization summary and confirm SSH, DNS, floating IP, Docker,
   application, and VPN behavior.
5. Run the play again and confirm normal-mode idempotency.
6. Reboot only when appropriate for the test environment, then rerun the role
   and verify persisted BBR/sysctl/performance state.
7. Expand to additional hosts only after the canary is clean.
