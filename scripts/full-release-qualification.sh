#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

export ANSIBLE_CONFIG="$repo_root/ansible.cfg"
export ANSIBLE_FORCE_COLOR="${ANSIBLE_FORCE_COLOR:-1}"
export PY_COLORS="${PY_COLORS:-1}"

echo "==> Repository release contracts"
python3 -m py_compile tests/release/repository_contracts.py
python3 tests/release/repository_contracts.py

echo
echo "==> Optimization capacity contracts"
ansible-playbook -i localhost, tests/release/optimization_contract.yml

echo
echo "==> Rendered artifact contracts"
ansible-playbook -i localhost, tests/release/render_contracts.yml

echo
echo "==> ShellCheck rendered scripts"
shellcheck \
  /tmp/ansible-release-artifacts/vpn-network-perf \
  /tmp/ansible-release-artifacts/abuse-defender-update.sh \
  /tmp/ansible-release-artifacts/pg-watchdog.sh

echo
echo "==> Verify rendered systemd unit"
systemd-analyze verify /tmp/ansible-release-artifacts/vpn-network-perf.service

echo
echo "==> Full release system integration and idempotency"
ANSIBLE_ROLES_PATH="$repo_root/roles" molecule test -s release_system

echo
echo "Full Release Qualification completed successfully."
echo "No production hosts, credentials, or provider APIs were used."
