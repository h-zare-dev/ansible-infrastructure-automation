#!/usr/bin/env bash
set -euo pipefail

INVENTORY="inventory/hosts.example.ini"

echo "==> Checking Git diff formatting"
git diff --check

echo
echo "==> Checking repository status"
git status --short

echo
echo "==> Running Ansible syntax checks"

echo
echo "---- playbooks/bootstrap.yml ----"
ansible-playbook \
  -i "$INVENTORY" \
  playbooks/bootstrap.yml \
  --syntax-check \
  -e bootstrap_host=example-node

playbooks=(
  "playbooks/site.yml"
  "playbooks/security.yml"
  "playbooks/operations/optimize.yml"
  "playbooks/operations/ping-control.yml"
  "playbooks/operations/security-updates.yml"
  "playbooks/operations/system-update.yml"
)

for playbook in "${playbooks[@]}"; do
  echo
  echo "---- $playbook ----"
  ansible-playbook \
    -i "$INVENTORY" \
    "$playbook" \
    --syntax-check
done

echo
echo "==> Checking required operational playbooks"

required_files=(
  "playbooks/operations/optimize.yml"
  "playbooks/operations/ping-control.yml"
  "playbooks/operations/security-updates.yml"
  "playbooks/operations/system-update.yml"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "ERROR: required file missing: $file"
    exit 1
  fi
done

echo
echo "==> Checking for accidentally tracked production files"

sensitive_files=(
  "inventory/hosts.ini"
  "inventory/group_vars/all/vault.yml"
)

for file in "${sensitive_files[@]}"; do
  if git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
    echo "ERROR: sensitive production file is tracked by Git: $file"
    exit 1
  fi
done

echo
echo "Validation completed successfully."
echo "No production hosts were contacted."
