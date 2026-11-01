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

bootstrap = load_yaml("playbooks/bootstrap.yml")
assert len(bootstrap) == 2
assert bootstrap[0]["hosts"] == "{{ bootstrap_host }}"
assert [role_name(item) for item in bootstrap[0]["roles"]] == ["controller_known_hosts"]

known_hosts_reset = load_yaml("roles/controller_known_hosts/tasks/main.yml")
assert len(known_hosts_reset) == 1
known_hosts_play = known_hosts_reset[0]
assert known_hosts_play["delegate_to"] == "localhost"
assert known_hosts_play["become"] is False
assert known_hosts_play["run_once"] is True
known_hosts_tasks = known_hosts_play["block"]
assert len(known_hosts_tasks) == 2
assert known_hosts_tasks[0]["ansible.builtin.file"]["state"] == "directory"
assert known_hosts_tasks[0]["ansible.builtin.file"]["mode"] == "0700"
known_hosts_copy = known_hosts_tasks[-1]["ansible.builtin.copy"]
assert known_hosts_copy["dest"] == "{{ controller_known_hosts_path }}"
assert known_hosts_copy["content"] == ""
assert known_hosts_copy["mode"] == "0600"
assert "ssh-keygen" not in (ROOT / "roles/controller_known_hosts/tasks/main.yml").read_text()

bootstrap_roles = [role_name(item) for item in bootstrap[1]["roles"]]
assert bootstrap_roles == [
    "ssh_security",
    "cloudflare_dns",
    "controller_ssh_config",
], bootstrap_roles
# Utility installation belongs to site.yml, not bootstrap.
assert "speedtest_cli" not in bootstrap_roles
assert "floatip_manager" not in bootstrap_roles
assert bootstrap[1]["vars"]["system_update_reboot"] is True
bootstrap_final_tasks = bootstrap[1]["tasks"]
assert len(bootstrap_final_tasks) == 4
assert bootstrap_final_tasks[0]["ansible.builtin.meta"] == "flush_handlers"
assert bootstrap_final_tasks[1]["ansible.builtin.meta"] == "reset_connection"
assert "ansible.builtin.wait_for_connection" in bootstrap_final_tasks[2]
assert bootstrap_final_tasks[-1]["ansible.builtin.include_role"]["name"] == "system_update"

debian_update = load_yaml("roles/system_update/tasks/debian.yml")
debian_task_names = [task["name"] for task in debian_update]
assert debian_task_names.index("Correct verified BIOS GRUB debconf target") < (
    debian_task_names.index("Upgrade installed packages")
)
assert debian_task_names.index("Stop unsafe GRUB upgrades before any APT changes") < (
    debian_task_names.index("Update APT package cache")
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
    assert play["hosts"] == "all", (path, play["hosts"])
    assert play["serial"] == 1, (path, play.get("serial"))

security_defaults = load_yaml("roles/security_updates/defaults/main.yml")
system_update_defaults = load_yaml("roles/system_update/defaults/main.yml")
optimization_defaults = load_yaml("roles/optimization/defaults/main.yml")

assert security_defaults["security_updates_reboot"] is False
assert system_update_defaults["system_update_reboot"] is False
assert optimization_defaults["optimization_live_qdisc_replace"] is False

floatip_defaults = load_yaml("roles/floatip_manager/defaults/main.yml")
assert floatip_defaults["floatip_manager_latest_release_url"].endswith(
    "/h-zare-dev/floatip-manager/releases/latest"
)
assert floatip_defaults["floatip_manager_fallback_ref"] == (
    "e541e59816647df25c771630e35c63eca532bde7"
)
assert floatip_defaults["floatip_manager_path"] == "/usr/local/sbin/floatip"
floatip_plan = load_yaml("roles/floatip_manager/tasks/main.yml")
floatip_task_names = [task["name"] for task in floatip_plan]
assert floatip_task_names.index(
    "Resolve latest stable FloatIP Manager release on controller"
) < floatip_task_names.index(
    "Install latest stable FloatIP Manager CLI on Hetzner hosts only"
)
floatip_release_lookup = next(
    task for task in floatip_plan
    if task["name"] == "Resolve latest stable FloatIP Manager release on controller"
)
assert floatip_release_lookup["delegate_to"] == "{{ floatip_manager_release_delegate }}"
assert floatip_release_lookup["become"] is False
assert floatip_release_lookup["run_once"] is True
assert floatip_release_lookup["ansible.builtin.uri"]["status_code"] == [200, 404]
floatip_install = next(
    task for task in floatip_plan
    if task["name"] == "Install latest stable FloatIP Manager CLI on Hetzner hosts only"
)
assert floatip_install["ansible.builtin.get_url"]["dest"] == "{{ floatip_manager_path }}"
assert "floatip_manager_selected_ref" in floatip_install["ansible.builtin.get_url"]["url"]
assert "hetzner" in floatip_install["when"]

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

optimization_paths = list((ROOT / "roles/optimization/tasks").glob("*.yml"))
optimization_tree = "\n".join(path.read_text() for path in optimization_paths)
for forbidden in (
    "/etc/netplan",
    "ufw",
    "resolvectl dns",
):
    assert forbidden not in optimization_tree.lower(), (
        "optimization must preserve its non-goals",
        forbidden,
    )


def iter_task_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_task_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_task_dicts(child)


for path in optimization_paths:
    data = load_yaml(str(path.relative_to(ROOT)))
    for task in iter_task_dicts(data):
        for module in ("ansible.builtin.systemd", "ansible.builtin.service"):
            args = task.get(module)
            if isinstance(args, dict):
                assert str(args.get("name", "")).lower() != "docker", (
                    "optimization must not manage Docker service state",
                    path,
                )

        for module in ("ansible.builtin.command", "ansible.builtin.shell"):
            args = task.get(module)
            if isinstance(args, str):
                command_text = args
            elif isinstance(args, dict):
                argv = args.get("argv", [])
                command_text = " ".join(map(str, argv))
                command_text += " " + str(args.get("cmd", ""))
            else:
                command_text = ""

            assert "docker restart" not in command_text.lower(), (
                "optimization must not restart Docker",
                path,
                command_text,
            )
            assert "systemctl restart docker" not in command_text.lower(), (
                "optimization must not restart Docker",
                path,
                command_text,
            )

print("Repository release contracts are valid.")
