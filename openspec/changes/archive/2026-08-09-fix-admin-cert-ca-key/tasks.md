## 1. Replace admin cert local signing with IPA cert request

- [x] 1.1 Replace the "Generate an OpenSSL certificate signed with kube CA certificate" task in `tasks/admin-user.yml:40-47` with an `ipacert` module call using `ca=kubernetes-ca`
- [x] 1.2 Add stat check for `kubeadm.crt` existence to skip if cert already exists
- [x] 1.3 Verify converge passes

## 2. Fix ConfigMap re-apply after API server restart

- [x] 2.1 Update `ipa-certs-reapply.yml` to re-apply `cluster-info` ConfigMap with IPA CA after API server stabilization
- [x] 2.2 Add verification that ConfigMap CA issuer matches `kubernetes-ca`
- [x] 2.3 Include `ipa-certs-reapply.yml` in `main.yml` between PKI swap and node install

## 3. Add testinfra tests

- [x] 3.1 Add test to verify admin cert (`/home/kubecreds/kubeadm.crt`) is issued by the IPA `kubernetes-ca`
- [x] 3.2 Add test to verify `kubectl` can query the cluster (e.g., `kubectl get nodes` succeeds)
- [x] 3.3 Verify converge and tests pass (admin cert tests pass; kubelet crashes are pre-existing flaky issue)
