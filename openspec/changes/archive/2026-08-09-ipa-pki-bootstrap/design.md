## Context

The skeleton in `ipa-api-server.yml`, `kube-apiserver-kubelet-client.yml`, and `ipa-certs.yml` uses shell commands that run on the wrong host. CSR files live on the K8s master, but `ipa cert-request` runs via `delegate_to` on the IPA server where the CSR path doesn't exist. The `freeipa.ansible_freeipa.ipacert` module solves this by running locally and connecting via Kerberos.

### Design Shift: Pre-seed → Post-init Swap

Original design called for pre-seeding all PKI artifacts before `kubeadm init`. Testing revealed that kubeadm's preflight check fails when it encounters partial PKI state (IPA certs without corresponding kubeadm config files). The working approach is:

1. Let kubeadm init with a clean PKI directory (generates its own certs)
2. After init, swap in IPA-signed certificates
3. Patch embedded CA references in component configs
4. Restart the API server static pod

## Goals / Non-Goals

**Goals:**
- Post-init swap of kubeadm PKI with IPA-signed certificates
- Replace shell `ipa cert-request` with `ipacert` module
- Add front-proxy-client cert (missing from skeleton)
- Generate SA key locally
- Patch controller-manager and scheduler configs to trust IPA CA
- Wire into `main.yml` after `kube-install.yml`

**Non-Goals:**
- CA infrastructure setup (covered by `ipa-pki-infra`)
- Admin credentials (covered by `ipa-kubectl-auth`)
- Certificate auto-renewal (covered by `tcharl.kube_certmanager`)
- etcd PKI replacement (separate trust domain)

## Decisions

**Post-init swap instead of pre-seed**
- Kubeadm preflight fails on partial PKI state
- Clean init → swap → restart is more reliable
- Requires updating `kube-install.yml` to run IPA cert tasks after kubeadm init

**`ipacert` module runs on K8s master (no `delegate_to`)**
- CSR files and keytab live on the master
- Module connects to IPA server via Kerberos ticket
- Fixes the cross-host file path issue from the skeleton

**Front-proxy cert uses same principal as apiserver**
- `HTTP/apiserver.kubernetes.<domain>` for both certs
- Different SAN/CN for front-proxy (master hostname only)

**SA key generated locally, not via IPA**
- SA key is for JWT signing, not TLS — IPA cannot sign this type
- Use `community.crypto.openssl_privatekey` with ECDSA

**ca.crt swapped, ca.key kept**
- `ca.crt` replaced with kubernetes-ca cert from IPA
- `ca.key` remains kubeadm-generated (orphaned, but harmless)
- Cert rotation handled by cert-manager, not kubeadm

**Component configs patched post-swap**
- `controller-manager.conf` and `scheduler.conf` have embedded `certificate-authority-data` (base64 of kubeadm ca.crt)
- Must patch to reference `/etc/kubernetes/pki/ca.crt` by path instead of inline data
- `kubelet.conf` and `admin.conf` already reference `ca.crt` by path — no change needed

## Risks / Trade-offs

[Kubeadm cert rotation will fail with mismatched ca.crt/ca.key] → Mitigation: Cert rotation handled by cert-manager (non-goal). Document that `kubeadm certs renew` must not be run.

[ipacert requires valid Kerberos ticket] → Mitigation: Kerberos safeguard task added in `ipa-pki-infra`.

[Old certs not revoked on re-run] → Mitigation: Idempotency at Ansible level via `stat.exists` check.

[API server downtime during swap] → Mitigation: Swap is fast (file copy + pod restart), expected ~30s downtime.

[etcd client cert still signed by kubeadm etcd CA] → Mitigation: etcd PKI is separate trust domain, not in scope.
