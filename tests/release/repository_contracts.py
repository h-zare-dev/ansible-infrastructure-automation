#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: str):
    return yaml.safe_load((ROOT / path).read_text())


def role_name(entry):
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("role")
    raise TypeError(entry)


role_dirs = {
    path.name
    for path in (ROOT / "roles").iterdir()
    if path.is_dir()
}
coverage = load_yaml("tests/release/role_coverage.yml")
classified = set().union(*(set(items) for items in coverage.values()))

assert classified == role_dirs, (
    "Every role must be classified for release qualification. "
    f"missing={sorted(role_dirs - classified)} "
    f"unknown={sorted(classified - role_dirs)}"
)

site = load_yaml("playbooks/site.yml")
managed_roles = [role_name(item) for item in site[0]["roles"]]
expected_managed_roles = [
    "ssh_security",
    "controller_ssh_config",
    "cloudflare_dns",
    "hostname",
    "dns_resolver",
    "base_packages",
    "speedtest_cli",
    "floatip_manager",
    "monitoring",
]
assert managed_roles == expected_managed_roles, managed_roles

node_roles = [role_name(item) for item in site[1]["roles"]]
assert node_roles == [
    "docker",
    "pasarguard",
    "pasarguard_watchdog",
    "abuse_firewall",
], node_roles

for path in [
    "playbooks/operations/security-updates.yml",
    "playbooks/operations/system-update.yml",
]:
    play = load_yaml(path)[0]
    assert play["hosts"] == "pasarguard_nodes", (path, play["hosts"])
    assert play["serial"] == 1, (path, play.get("serial"))

security_defaults = load_yaml("roles/security_updates/defaults/main.yml")
system_update_defaults = load_yaml("roles/system_update/defaults/main.yml")
optimization_defaults = load_yaml("roles/optimization/defaults/main.yml")

assert security_defaults["security_updates_reboot"] is False
assert system_update_defaults["system_update_reboot"] is False
assert optimization_defaults["optimization_live_qdisc_replace"] is False

floatip_tasks = (ROOT / "roles/floatip_manager/tasks/main.yml").read_text()
for forbidden in ("netplan", "ip addr", "ip route", "systemd-networkd"):
    assert forbidden not in floatip_tasks, (
        "floatip_manager installer role must not manage live networking",
        forbidden,
    )

cloudflare_tasks = (ROOT / "roles/cloudflare_dns/tasks/main.yml").read_text()
assert "delegate_to: localhost" in cloudflare_tasks
assert 'api_token: "{{ cf_api_token }}"' in cloudflare_tasks
assert "proxied: false" in cloudflare_tasks
assert "solo: true" in cloudflare_tasks

docker_defaults = load_yaml("roles/docker/defaults/main.yml")
assert docker_defaults["docker_architecture"] == "amd64"
assert docker_defaults["docker_gpg_key_path"].endswith("/docker.asc")
assert {
    "docker-ce",
    "docker-ce-cli",
    "containerd.io",
    "docker-buildx-plugin",
    "docker-compose-plugin",
} <= set(docker_defaults["docker_packages"])

optimization_tree = "\n".join(
    path.read_text()
    for path in (ROOT / "roles/optimization/tasks").glob("*.yml")
)
for forbidden in (
    "/etc/netplan",
    "ufw",
    "resolvectl dns",
    "docker restart",
    "systemctl restart docker",
):
    assert forbidden not in optimization_tree.lower(), (
        "optimization must preserve its non-goals",
        forbidden,
    )

print("Repository release contracts are valid.")
