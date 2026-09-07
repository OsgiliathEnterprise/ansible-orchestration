## Why

The admin-user certificate signing in `tasks/admin-user.yml:40-47` uses `community.crypto.x509_certificate` with the `ownca` provider, referencing the kubeadm-generated `ca.key` at `/etc/kubernetes/pki/ca.key`. This key is replaced during the IPA PKI swap, so the admin cert is locally-signed instead of IPA-signed like all other control plane certificates.

## What Changes

- Replace the local `ownca` signing task with a `freeipa.ansible_freeipa.ipacert` module call using `ca=kubernetes-ca`
- Add a stat check to skip if `kubeadm.crt` already exists
- Add testinfra tests to verify the admin cert is IPA-signed and that `kubectl` can query the cluster

## Capabilities

### Modified Capabilities
- `ipa-pki-bootstrap`: admin cert uses IPA CA via ipacert module

## Impact

- `tasks/admin-user.yml`: replace ownca task with ipacert module call
- `molecule/default/tests/test_master.py`: add admin cert IPA-signed test and kubectl cluster query test
