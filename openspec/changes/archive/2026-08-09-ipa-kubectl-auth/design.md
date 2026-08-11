## Context

The `admin-user.yml` generates a self-signed admin cert using `community.crypto.x509_certificate` with `provider: ownca`, signing against the local kubeadm CA. The kubeconfig references this self-signed cert. When IPA PKI is enabled, the admin cert should be IPA-signed and the kubeconfig should trust `kubernetes-ca`.

With the post-init swap approach from `ipa-pki-bootstrap`, `ca.crt` at `/etc/kubernetes/pki/ca.crt` will already be the `kubernetes-ca` certificate. Since `kubelet.conf` and `admin.conf` reference `ca.crt` by path, they'll automatically trust the IPA CA after the swap.

## Goals / Non-Goals

**Goals:**
- Replace ownca admin cert with `ipacert` module
- Wire kubeconfig to trust `kubernetes-ca` as certificate authority (already handled by path reference to `ca.crt`)
- Add cleanup tasks for IPA cert revocation and DNS/service principal removal
- Maintain backward compatibility (ownca path when `use_ipa_pki: false`)

**Non-Goals:**
- CA infrastructure setup (covered by `ipa-pki-infra`)
- Bootstrap certs (covered by `ipa-pki-bootstrap`)
- Certificate auto-renewal (covered by `tcharl.kube_certmanager`)

## Decisions

**Conditional signing path in admin-user.yml**
- use `ipacert` module with `ca: kubernetes-ca`, `profile_id: kubeAdministrators`
- When `false`/undefined: keep existing `ownca` provider
- CSR generation stays the same in both paths

**Kubeconfig CA already trusts IPA CA**
- `admin.conf` references `/etc/kubernetes/pki/ca.crt` by path
- After `ipa-pki-bootstrap` swap, `ca.crt` is the `kubernetes-ca` cert
- No explicit `kubectl config set-cluster` needed — trust is automatic
- When `use_ipa_pki: false`, `ca.crt` is kubeadm's CA (existing behavior)

**Cleanup on teardown**
- Revoke IPA-signed certs via `ipacert` module with `state: revoked`
- Remove IPA DNS records and service principals via delegated shell commands

## Risks / Trade-offs

[Revocation may fail if cert already revoked] → Mitigation: `failed_when: false` on revocation tasks.

[Self-signed path must remain functional] → Mitigation: Conditional logic preserves existing behavior.
