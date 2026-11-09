#!/usr/bin/env bash
# Bootstrap the Production Ansible controller on a new Ubuntu installation.
# NEVER run a playbook against remote inventory hosts from this installer.
set -euo pipefail

repository_url="https://github.com/h-zare-dev/ansible-infrastructure-automation.git"
repository_dir="/root/ansible-project"
venv="/opt/ansible-controller-venv"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Run as root." >&2
  exit 1
fi
if [[ ! -f /etc/os-release ]]; then
  echo "ERROR: Cannot identify operating system." >&2
  exit 1
fi
# shellcheck source=/dev/null
source /etc/os-release
if [[ "$ID" != "ubuntu" ]]; then
  echo "ERROR: This installer supports Ubuntu only." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  git python3 python3-venv python3-pip openssh-client age ca-certificates

if [[ ! -e "$repository_dir" ]]; then
  git clone --branch main --single-branch "$repository_url" "$repository_dir"
else
  if [[ ! -d "$repository_dir/.git" ]]; then
    echo "ERROR: Existing target directory is not a Git repository." >&2
    exit 1
  fi
  remote="$(git -C "$repository_dir" remote get-url origin)"
  if [[ "$remote" != "$repository_url" && "$remote" != "https://github.com/h-zare-dev/ansible-infrastructure-automation" ]]; then
    echo "ERROR: Unexpected origin remote; refusing to replace it." >&2
    exit 1
  fi
  if [[ "$(git -C "$repository_dir" branch --show-current)" != "main" ]]; then
    echo "ERROR: Production controller must be on branch main." >&2
    exit 1
  fi
  if [[ -n "$(git -C "$repository_dir" status --porcelain --untracked-files=normal)" ]]; then
    echo "ERROR: Local Git changes detected; review them before running installer." >&2
    exit 1
  fi
  git -C "$repository_dir" pull --ff-only origin main
fi

if [[ ! -x "$venv/bin/python" ]]; then
  python3 -m venv "$venv"
fi
"$venv/bin/python" -m pip install --disable-pip-version-check "ansible-core==2.21.5"
"$venv/bin/ansible-galaxy" collection install -r "$repository_dir/requirements.yml"

export PATH="$venv/bin:$PATH"
export ANSIBLE_VAULT_PASSWORD_FILE="/root/.ansible/vault_pass"
cd "$repository_dir"
echo "Installed Git, Ansible, collections and age. Starting local-only setup."
exec python3 scripts/controller_manager.py --vault-binary "$venv/bin/ansible-vault" install
