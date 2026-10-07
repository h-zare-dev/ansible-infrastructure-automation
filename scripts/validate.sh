#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

export ANSIBLE_CONFIG="$repo_root/ansible.cfg"

# Isolate example group vars from any ignored production files beside them.
inventory_dir="$(mktemp -d)"
trap 'rm -rf -- "$inventory_dir"' EXIT
mkdir -p "$inventory_dir/group_vars/all"
cp inventory/hosts.example.ini "$inventory_dir/hosts.example.ini"
cp inventory/group_vars/all/vars.yml "$inventory_dir/group_vars/all/vars.yml"
cp inventory/group_vars/all/vault.yml.example "$inventory_dir/group_vars/all/vault.yml"
cp inventory/group_vars/ssh_ubuntu.yml "$inventory_dir/group_vars/ssh_ubuntu.yml"
export ANSIBLE_INVENTORY="$inventory_dir/hosts.example.ini"
INVENTORY="$ANSIBLE_INVENTORY"

echo "==> Checking Git diff formatting"
if [[ -n "${CI_BASE_SHA:-}" ]]; then
  git cat-file -e "${CI_BASE_SHA}^{commit}"
  git diff --check "${CI_BASE_SHA}...HEAD"
else
  git diff --check
fi

echo
echo "==> Checking repository status"
git status --short

echo
echo "==> Running yamllint"
yaml_targets=(
  .yamllint
  .ansible-lint
  .github/workflows
  molecule
  tests/release
  requirements.yml
  inventory/group_vars/all/vars.yml
  inventory/group_vars/all/vault.yml.example
  inventory/group_vars/ssh_ubuntu.yml
  playbooks
  roles
)
yamllint -f parsable "${yaml_targets[@]}"

echo
echo "==> Running ansible-lint"
ansible-lint --offline playbooks roles molecule tests/release

echo
echo "==> Running Ansible syntax checks with example inventory"

echo
echo "---- playbooks/bootstrap.yml ----"
ansible-playbook -i "$INVENTORY" playbooks/bootstrap.yml \
  --syntax-check -e bootstrap_host=node-01

mapfile -d '' -t playbooks < <(
  find playbooks -type f \( -name '*.yml' -o -name '*.yaml' \) -print0 | sort -z
)

for playbook in "${playbooks[@]}"; do
  if [[ "$playbook" == "playbooks/bootstrap.yml" ]]; then
    continue
  fi
  echo
  echo "---- $playbook ----"
  ansible-playbook -i "$INVENTORY" "$playbook" --syntax-check
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

if git ls-files | grep -Eq '(^|/)(ansible_ssh_key|id_(rsa|ed25519|ecdsa|dsa))(\..*)?$'; then
  echo "ERROR: a private-key-style filename is tracked by Git:"
  git ls-files | grep -E '(^|/)(ansible_ssh_key|id_(rsa|ed25519|ecdsa|dsa))(\..*)?$'
  exit 1
fi

if git grep -n -I -E -e '-----BEGIN (OPENSSH|RSA|EC|DSA) PRIVATE KEY-----' -- .; then
  echo "ERROR: tracked private key material detected."
  exit 1
fi

echo
echo "Validation completed successfully."
echo "No production hosts were contacted."
