## Why

The `admin-user.yml` file generates a self-signed admin certificate using the local kubeadm CA, and the kubeconfig trusts that self-signed CA. This disconnects kubectl authentication from the platform's centralized trust. This change replaces the admin cert with an IPA-signed certificate and wires the kubeconfig to trust the `kubernetes-ca`.

## What Changes

- Replace `community.crypto.x509_certificate` with `ownca` provider by `freeipa.ansible_freeipa.ipacert` module for admin cert
- Wire kubeconfig to trust `kubernetes-ca` certificate as `certificate-authority`
- Add cleanup tasks to revoke IPA certificates and remove IPA DNS/service principals on cluster teardown

## Capabilities

### New Capabilities
- `ipa-kubectl-auth`: IPA-signed admin credentials and kubeconfig trust chain for kubectl authentication

### Modified Capabilities

## Impact

- **Affected code**: `admin-user.yml`, `delete.yml`
- **Dependencies**: Requires `ipa-pki-infra` and `ipa-pki-bootstrap` changes
- **Backward compatibility**: Gated by `use_ipa_pki` variable
