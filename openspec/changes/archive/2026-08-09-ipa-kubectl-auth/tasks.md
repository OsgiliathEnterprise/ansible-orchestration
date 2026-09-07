## 1. Admin Certificate (admin-user.yml)

- [x] 1.1 Add conditional: use `ipacert` module instead of `ownca`
- [x] 1.2 Set `ca: kubernetes-ca`, `profile_id: kubeAdministrators` for admin cert request
- [x] 1.4 Ensure CSR generation stays the same in both paths

## 2. Kubeconfig Trust Chain (admin-user.yml)

- [x] 2.1 Verify kubeconfig references `/etc/kubernetes/pki/ca.crt` by path (no explicit set-cluster needed — trust is automatic after ipa-pki-bootstrap swap)
- [x] 2.2 Set kubeconfig `client-certificate` to `/home/kubecreds/kubeadm.crt`
- [x] 2.3 Set kubeconfig `client-key` to `/home/kubecreds/kubeadm.pem`
- [x] 2.4 Verify `kubectl` commands work with IPA-signed credentials

## 3. Cleanup on Teardown (delete.yml)

- [x] 3.1 Add task to revoke IPA-signed certificates via `ipacert` module with `state: revoked`
- [x] 3.2 Add task to remove IPA DNS record for `apiserver.kubernetes.<domain>`
- [x] 3.3 Add task to remove IPA service principal `HTTP/apiserver.kubernetes.<domain>`
- [x] 3.4 Gate cleanup tasks with `reset_kube: true`
- [x] 3.5 Use `failed_when: false` on revocation tasks (cert may already be revoked)

## 4. Testinfra Tests

- [x] 4.1 Add test: admin cert at `/home/kubecreds/kubeadm.crt` is signed by `kubernetes-ca`
- [x] 4.2 Add test: kubeconfig references `kubernetes-ca` as certificate authority when `use_ipa_pki: true`
- [x] 4.3 Add test: kubeconfig references IPA-signed cert as client certificate
- [x] 4.4 Add test: `kubectl get nodes` succeeds with IPA-signed credentials
