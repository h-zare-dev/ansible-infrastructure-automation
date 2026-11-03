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
echo "==> Running isolated GRUB preflight policy tests"
python3 -m unittest discover -s tests/release -p 'test_grub_preflight.py' -v

echo
echo "==> Checking operational failure and CI security contracts"
python3 -m unittest discover -s tests/release -p 'test_operational_hardening.py' -v

echo
echo "==> Checking automatic Bootstrap marker and discovery contracts"
python3 -m unittest discover -s tests/release -p 'test_bootstrap_auto.py' -v

echo
echo "==> Verifying safe read-only PasarGuard certificate viewing"
python3 -m unittest discover -s tests/release -p 'test_pasarguard_certificate.py' -v
# Generate a disposable local certificate and intentionally append its private
# key. The show-only playbook MUST print just the X.509 public certificate.
cert_fixture_dir="$inventory_dir/cert-fixture"
mkdir -p -- "$cert_fixture_dir"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj "/CN=ci.example.invalid" \
  -keyout "$cert_fixture_dir/private.key" \
  -out "$cert_fixture_dir/public.pem" >/dev/null 2>&1
cat "$cert_fixture_dir/public.pem" "$cert_fixture_dir/private.key" > "$cert_fixture_dir/combined.pem"
cert_view_log="$(mktemp)"
if ! ansible-playbook -i "$INVENTORY" -c local \
  playbooks/operations/show-pasarguard-certificate.yml \
  --limit node-01 \
  -e ansible_become=false \
  -e "pasarguard_cert_path=$cert_fixture_dir/combined.pem" \
  >"$cert_view_log" 2>&1; then
  cat "$cert_view_log"
  rm -f -- "$cert_view_log"
  exit 1
fi
cat "$cert_view_log"
grep -Fq -- 'BEGIN CERTIFICATE' "$cert_view_log"
grep -Fq -- 'SHA256 Fingerprint' "$cert_view_log"
if grep -Eq -- 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|unreachable=[1-9]|failed=[1-9]|changed=[1-9]' "$cert_view_log"; then
  echo "ERROR: certificate view exposed a private key or changed/failed."
  rm -f -- "$cert_view_log"
  exit 1
fi
rm -f -- "$cert_view_log"

echo
echo "==> Running isolated read-only Bootstrap previews against CI fixtures"
# Keep the CI fixture independent of the production controller's real SSH key.
# The marker probe runs locally; the fixture key is never a usable credential.
bootstrap_fixture_pubkey="$inventory_dir/bootstrap-fixture.pub"
printf 'ssh-ed25519 %s bootstrap-ci-fixture\n' 'dGVzdGZpeHR1cmU=' > "$bootstrap_fixture_pubkey"
ansible-playbook -i "$INVENTORY" -c local playbooks/bootstrap-auto.yml \
  --limit node-01 \
  -e '{"bootstrap_auto_discover_only": true, "bootstrap_probe_command": "printf MARKED"}'
ansible-playbook -i "$INVENTORY" -c local playbooks/bootstrap-auto.yml \
  --limit node-01 \
  -e '{"bootstrap_auto_discover_only": true, "bootstrap_probe_command": "printf NEW"}' \
  -e "vault_ssh_public_key_path=$bootstrap_fixture_pubkey"

echo
echo "==> Checking zero-candidate Auto Bootstrap remains warning-free and idempotent"
# Exercise the real non-preview Auto Bootstrap path against a local CI fixture.
# With a valid mocked marker, no host must enter SSH hardening or OS updates.
# Do NOT globally disable host-pattern mismatch warnings in ansible.cfg.
bootstrap_noop_log="$(mktemp)"
if ! ansible-playbook -i "$INVENTORY" -c local playbooks/bootstrap-auto.yml \
  --limit node-01 \
  -e '{"bootstrap_probe_command": "printf MARKED"}' >"$bootstrap_noop_log" 2>&1; then
  cat "$bootstrap_noop_log"
  rm -f -- "$bootstrap_noop_log"
  exit 1
fi
cat "$bootstrap_noop_log"
if grep -Eq 'Could not match supplied host pattern|ignoring: __bootstrap_auto_pending|changed=[1-9]|failed=[1-9]|unreachable=[1-9]' "$bootstrap_noop_log"; then
  echo "ERROR: no-candidate Auto Bootstrap produced a mismatch warning or modified a host."
  rm -f -- "$bootstrap_noop_log"
  exit 1
fi
rm -f -- "$bootstrap_noop_log"

echo
echo "==> Verifying two-host automatic discovery runs without serialization"
# Local CI fixtures only. Exercises multiple managed hosts with no
# controller SSH changes, provider API calls, or system updates.
parallel_noop_log="$(mktemp)"
if ! ansible-playbook -i "$INVENTORY" -c local playbooks/bootstrap-auto.yml \
  --limit node-01,node-02 -f 5 \
  -e '{"bootstrap_probe_command": "printf MARKED"}' >"$parallel_noop_log" 2>&1; then
  cat "$parallel_noop_log"
  rm -f -- "$parallel_noop_log"
  exit 1
fi
cat "$parallel_noop_log"
if grep -Eq 'Could not match supplied host pattern|changed=[1-9]|failed=[1-9]|unreachable=[1-9]' "$parallel_noop_log"; then
  echo "ERROR: two-host Auto Bootstrap no-op modified hosts or showed errors."
  rm -f -- "$parallel_noop_log"
  exit 1
fi
grep -Fq '"node-01"' "$parallel_noop_log"
grep -Fq '"node-02"' "$parallel_noop_log"
rm -f -- "$parallel_noop_log"

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
  # Shared vars/*.yml are YAML mappings, not executable playbooks.
  if [[ "$playbook" == "playbooks/bootstrap.yml" || "$playbook" == playbooks/vars/* ]]; then
    continue
  fi
  echo
  echo "---- $playbook ----"
  ansible-playbook -i "$INVENTORY" "$playbook" --syntax-check
done

echo
echo "==> Validating release note extraction"
release_notes_tmp="$(mktemp)"
python3 scripts/extract-release-notes.py \
  --version v1.0.0 \
  --output "$release_notes_tmp"
test -s "$release_notes_tmp"
rm -f -- "$release_notes_tmp"

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
