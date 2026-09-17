## 1. Wire IPA Certs into Main Pipeline

- [x] 1.1 Uncomment `ipa-certs.yml` include in `main.yml`
- [x] 1.2 Place `ipa-certs.yml` AFTER `kube-install.yml` in execution order (post-init swap)
- [x] 1.3 Ensure `ipa-certs.yml` only runs on `kube_masters_group` hosts
- [x] 1.4 Ensure `/etc/kubernetes/pki` is cleaned before kubeadm init (so kubeadm generates clean PKI)

## 2. Kerberos Safeguard (ipa-certs.yml)

- [x] 2.1 Add `kinit -kt /etc/krb5.keytab` task at start of `ipa-certs.yml`
- [x] 2.2 Gate with `kube_masters_group`

## 3. CA Certificate Download (ipa-certs.yml)

- [x] 3.1 Ensure `ca.crt` is downloaded from `kubernetes-ca` to `/etc/kubernetes/pki/ca.crt`
- [x] 3.2 Set proper ownership (root:root) and mode (0644)
- [x] 3.3 Idempotent: skip if file exists and is already from kubernetes-ca

## 4. API Server Certificate (ipa-api-server.yml)

- [x] 4.1 Keep DNS record, IPA host, HTTP service principal tasks (delegated to IPA server)
- [x] 4.2 Keep CSR generation via `community.crypto.openssl_csr`
- [x] 4.3 Replace shell `ipa cert-request` with `freeipa.ansible_freeipa.ipacert` module
- [x] 4.4 Set `ca: kubernetes-ca`, `principal: HTTP/apiserver.kubernetes.{{ company_domain }}`, `certificate_out: /etc/kubernetes/pki/apiserver.crt`

## 5. Front-Proxy Client Certificate (NEW: ipa-front-proxy.yml)

- [x] 5.1 Create new `ipa-front-proxy.yml` task file
- [x] 5.2 Generate private key at `/etc/kubernetes/pki/front-proxy-client.key`
- [x] 5.3 Generate CSR with CN matching master hostname, `clientAuth` extended key usage
- [x] 5.4 Request certificate via `ipacert` module with `ca: kubernetes-ca`

## 6. Kubelet Client Certificate (kube-apiserver-kubelet-client.yml)

- [x] 6.1 Keep CSR generation via `community.crypto.openssl_csr`
- [x] 6.2 Replace shell `ipa cert-request` with `freeipa.ansible_freeipa.ipacert` module
- [x] 6.3 Set `ca: kubernetes-ca`, `profile_id: kubeAdministrators`, `certificate_out` path

## 7. SA Key Generation (ipa-certs.yml)

- [x] 7.1 Add SA key generation via `community.crypto.openssl_privatekey` at `/etc/kubernetes/pki/sa.key`
- [x] 7.2 Use ECDSA key type (matching kubeadm defaults)
- [x] 7.3 Idempotent: skip if file exists

## 8. Component Config Patching (NEW: ipa-pki-swap.yml)

- [x] 8.1 Patch `controller-manager.conf` to reference `/etc/kubernetes/pki/ca.crt` instead of embedded `certificate-authority-data`
- [x] 8.2 Patch `scheduler.conf` to reference `/etc/kubernetes/pki/ca.crt` instead of embedded `certificate-authority-data`
- [x] 8.3 Restart API server static pod via `crictl` or `kubectl rollout restart deployment kube-apiserver -n kube-system`
- [x] 8.4 Restart controller-manager and scheduler static pods

## 9. Orchestrator Tasks (ipa-certs.yml)

- [x] 9.1 Reorder: Kerberos safeguard → CA cert download → apiserver → front-proxy → kubelet-client → SA key → config patching → restart
- [x] 9.2 Ensure all tasks have `become: true` for master-side operations

## 10. Testinfra Tests

- [x] 10.1 Add test: `ca.crt` exists at `/etc/kubernetes/pki/ca.crt
- [x] 10.2 Add test: `apiserver.crt` and `apiserver.key` exist in `/etc/kubernetes/pki/`
- [x] 10.3 Add test: `front-proxy-client.crt` and `front-proxy-client.key` exist in `/etc/kubernetes/pki/`
- [x] 10.4 Add test: `apiserver-kubelet-client.crt` exists in `/etc/kubernetes/pki/`
- [x] 10.5 Add test: `sa.key` exists in `/etc/kubernetes/pki/`
- [x] 10.6 Add test: `apiserver.crt` is signed by `kubernetes-ca` (verify issuer CN)
- [x] 10.7 Add test: `controller-manager.conf` references `/etc/kubernetes/pki/ca.crt`
- [x] 10.8 Add test: `scheduler.conf` references `/etc/kubernetes/pki/ca.crt`
- [x] 10.9 Add test: kubeadm init succeeds with clean PKI
- [x] 10.10 Add test: API server static pod is running after swap
