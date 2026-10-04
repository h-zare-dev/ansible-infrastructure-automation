# Native VPN Optimization

`playbooks/operations/optimize.yml` applies the repository-owned `optimization`
role. The role no longer downloads or executes a remote optimization script.

## Scope

The role is intentionally limited to host performance settings that are useful
for PasarGuard/Xray VPN nodes:

- BBR when the running kernel exposes it, with a safe congestion-control fallback.
- RAM-aware accept queues, socket buffers, and conntrack capacity.
- Optional user-count-aware conntrack sizing via `optimization_expected_users`.
- TCP path hardening and PMTU black-hole probing.
- Loose reverse-path filtering for VPS, tunnel, and floating-IP compatibility.
- External TCP listener reservation inside the ephemeral port range.
- File-descriptor ceilings without restarting Docker or application containers.
- RPS/RFS/XPS on under-queued NICs through a generated oneshot systemd service.
- Optional CPU governor and THP modes; both preserve the current host state by default.
- Journald disk caps and NTP enablement.
- Safe retirement of conflicting files left by the former ServerTools integration.
- Pre/post verification that the default route, interface IPv4 addresses, resolver
  file, live qdisc (by default), and running Docker container set were not changed.

## Deliberately not managed

The optimization role does not own:

- DNS resolver configuration.
- Interface MTU or Netplan/networkd addressing.
- UFW or firewall policy.
- IPv6 disablement.
- Docker daemon restarts.
- Application/container restarts.
- Swap creation or removal.
- `tcp_tw_reuse`, `tcp_fastopen`, `tcp_no_metrics_save`, SACK, timestamps,
  fixed UDP memory pools, or NIC ring resizing.
- Live root-qdisc replacement unless `optimization_live_qdisc_replace=true`
  is explicitly supplied.

These boundaries avoid overlap with dedicated roles and avoid high-risk
network changes during an optimization run.

## Capacity tiers

The role selects a tier from total RAM and never lowers an already higher live
capacity value.

| Tier | RAM | somaxconn | netdev backlog | buffer ceiling | conntrack target |
| --- | ---: | ---: | ---: | ---: | ---: |
| S | <= 1.5 GB | 8,192 | 16,384 | 8 MiB | 65,536 |
| M | <= 6 GB | 16,384 | 32,768 | 16 MiB | 262,144 |
| L | <= 24 GB | 32,768 | 65,536 | 32 MiB | 1,048,576 |
| XL | > 24 GB | 65,535 | 65,536 | 64 MiB | 2,097,152 |

If `optimization_expected_users` is greater than zero, conntrack demand is
calculated from the expected online-user count while buffer ceilings remain
RAM-tier based.

## Default production run

```bash
ansible-playbook playbooks/operations/optimize.yml
```

The default target remains `pasarguard_nodes`.

## Test-host run

The operational playbook supports an explicit host-pattern override without
changing the production default:

```bash
ansible-playbook playbooks/operations/optimize.yml \
  -e optimize_hosts=Test-DE
```

Recommended Test-DE validation sequence:

1. Record a Speedtest result before the run.
2. Run the playbook once and review the optimization summary.
3. Confirm normal SSH, DNS, Floating IP, PasarGuard/Docker and VPN behavior.
4. Run Speedtest again using the same Ookla server ID.
5. Run the playbook a second time and confirm idempotency.
6. Reboot the test host only after the live test passes, then rerun the
   playbook and verify BBR, sysctl and RPS persistence.

Do not promote to production until the test-host run and reboot validation are
clean.
