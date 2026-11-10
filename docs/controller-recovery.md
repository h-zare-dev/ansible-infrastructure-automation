# Production controller: install, encrypted backup, restore and repair

**Scope:** /root/ansible-project on main only. The development checkout,
remote managed hosts, and /opt/sql_backup are never touched by these tools.

## Fresh or restored Ubuntu server

After reviewing the source, download the bootstrap installer from the PUBLIC
main branch (only after this feature has been merged and promoted):

    curl -fsSLo /root/install-controller.sh \
      https://raw.githubusercontent.com/h-zare-dev/ansible-infrastructure-automation/main/scripts/install-controller.sh
    bash /root/install-controller.sh

This installs Git, Python, SSH client and age; clones or fast-forwards
the public main repository at /root/ansible-project; installs pinned Ansible
Core into /opt/ansible-controller-venv and Galaxy collections. Existing
Git changes, unexpected origin remotes and other directories are not overwritten.

An interactive menu offers:

1. **Fresh:** asks for all six values in vault.yml.example:
   vault_ansible_password, vault_ansible_become_pass, vault_cf_api_token,
   vault_common_api_key, vault_domain_suffix, vault_ssh_public_key_path
   (the last is auto-populated with the known controller key path).
   It asks for a NEW Vault password twice, stores it at
   /root/.ansible/vault_pass (0600), creates an encrypted Vault, and creates
   an Ed25519 controller keypair. Import an existing Inventory file or choose
   an empty inventory that must be populated before managing remote hosts.
2. **Restore:** selects a downloaded encrypted archive and the age private
   recovery identity, checks integrity, restores the five essential files
   into *absent* target locations, verifies Vault/keypair and rebuilds
   controller-only SSH shortcut aliases from Inventory.
3. **Repair/Verify:** verifies essential files, Vault decryption and
   the matching SSH keypair, and creates the minimal SSH IdentityFile
   setting if absent. Does NOT overwrite existing credentials.

Neither installation, repair nor restore runs site.yml, bootstrap.yml,
system-update.yml or remote Ansible roles.

## Five required private files

1. /root/ansible-project/inventory/hosts.ini
2. /root/ansible-project/inventory/group_vars/all/vault.yml
3. /root/.ansible/vault_pass
4. /root/.ssh/ansible_ssh_key
5. /root/.ssh/ansible_ssh_key.pub

A manifest contains the production Git SHA and SHA-256 digests. All five
entries are packaged into tar.gz and **encrypted with age** before upload.
No age private decryption key is stored *inside* the archive. The public
code is obtained from GitHub; exact commit SHA is included in the manifest.

The SSH config file is NOT backed up: the known Host * IdentityFile rule is
recreated and aliases are regenerated from Inventory via the local-only
controller-ssh-shortcuts.yml playbook, using the existing controller role.
If custom SSH config directives are later added, revisit this assumption.

## Enable age and Telegram delivery

On a trusted separate device generate an age identity with age-keygen and
store the **private identity securely OFF the Ansible server**. Transfer
ONLY its public recipient (age1...) to the controller's interactive setup.
Alternatively the setup can create an age identity on the controller; then
you MUST copy the private identity off-server before enabling the timer.
The generated identity lives under:
  /root/.config/ansible-controller-backup/age-identity.txt
The backup never includes this decryption identity. If the server and the
offline copy are both lost, no Telegram backup can be decrypted.

The interactive installer offers encryption/Telegram configuration. It writes:
  /etc/ansible-controller-backup/age-recipient.txt
  /etc/ansible-controller-backup/telegram.json
The Telegram JSON contains bot_token and chat_id and is mode 0600.
Use a dedicated fresh Telegram bot token. Rotate any token previously
exposed in terminal logs or chat.

To configure later:

    cd /root/ansible-project
    python3 scripts/controller_manager.py configure-backup

The setup optionally runs the initial encrypted backup with an actual
Telegram API response check and only then enables daily scheduling.
The independent entrypoints are:

    ansible-playbook playbooks/operations/controller-backup.yml
    ansible-playbook playbooks/operations/controller-backup.yml \
      -e controller_backup_upload=false
    ansible-playbook playbooks/operations/controller-backup-schedule.yml
    ansible-playbook playbooks/operations/controller-restore.yml
    ansible-playbook playbooks/operations/controller-repair.yml

The timer runs at 03:00 controller-local time (+ up to 10 minutes random
delay) and uses Persistent=true to catch up after downtime. All backed-up
files must be present, Vault password and SSH private-key permissions must
not be broader than 0600, Git checkout must be clean and on main, and the
age recipient file must exist.

## Recover after total server loss

1. Provision a clean Ubuntu controller and securely download the installer.
2. Choose Restore. Provide the archive downloaded from Telegram and the
   offline age private recovery identity. Restore refuses to overwrite
   existing private files or extract arbitrary paths.
3. Verify Vault password file and SSH pair, then regenerate local aliases.
4. Verify access to managed servers manually with read-only SSH commands;
   no Ansible remote operations happen automatically.
5. Reconfigure Telegram delivery or provide an existing public recipient
   and reactivate daily backups only after verifying offline key custody.

If Telegram split the encrypted archive, download each part and concatenate
them in part-number order before verification and recovery:

    cat backup.tar.gz.age.part001 backup.tar.gz.age.part002 > backup.tar.gz.age

Use exact filenames; concatenating encrypted pieces works because splitting
occurs *after* encryption.

You can verify the archive independently:

    python3 scripts/controller_manager.py verify \
      --archive /root/backup.tar.gz.age \
      --identity /secure/offline-identity.txt

The file /root/.ansible/vault_pass is deliberately INSIDE the age-encrypted
archive. Therefore forgetting the old **Vault** password will not block
recovery. You still must have the **age private identity**.

Security boundaries: plaintext staging uses /run tmpfs, root-only
directories, checksum verification and strict tar member paths. Telegram
upload failure does not delete the local encrypted archive. Local archives
are NOT silently deleted; configure secure retention or move them to
secondary storage deliberately. Never store recovery keys in Git or send
them to Telegram.

CI uses dummy fixture files, loopback-only environments and disposable
age keys; production deployment and end-to-end disaster-recovery tests
must be done by the operator in a separate Ubuntu VM before relying on it.
