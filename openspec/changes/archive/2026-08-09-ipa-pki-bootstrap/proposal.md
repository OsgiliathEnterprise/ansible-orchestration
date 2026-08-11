## Why

Kubeadm generates self-signed certificates at install time, with no trust chain to the platform's FreeIPA PKI. This change pre-seeds IPA-signed certificates into `/etc/kubernetes/pki/` before `kubeadm init`, replacing shell-based `ipa cert-request` calls with the `freeipa.ansible_freeipa.ipacert` module. Certificates include: apiserver, front-proxy-client, kubelet-client, and the kubernetes-ca trust anchor.

## What Changes

- Pre-seed `ca.crt` (kubernetes-ca), `apiserver.crt/key`, `front-proxy-client.crt/key`, `apiserver-kubelet-client.crt/key`, and `sa.key` before kubeadm init
- Replace shell-based `ipa cert-request` with `freeipa.ansible_freeipa.ipacert` module
- Create new `ipa-front-proxy.yml` task file (currently missing from skeleton)
- Wire `ipa-certs.yml` into `main.yml` execution order before `kube-install.yml`
- All cert requests run on K8s master using keytab auth (no `delegate_to`, no password-in-shell)

## Capabilities

### New Capabilities
- `ipa-pki-bootstrap`: Pre-seed IPA-signed certificates into `/etc/kubernetes/pki/` before kubeadm init

### Modified Capabilities

## Impact

- **Affected code**: `ipa-certs.yml`, `ipa-api-server.yml`, `kube-apiserver-kubelet-client.yml`, `main.yml`
- **New code**: `ipa-front-proxy.yml`
- **Dependencies**: Requires `ipa-pki-infra` change (kubernetes-ca must exist)
