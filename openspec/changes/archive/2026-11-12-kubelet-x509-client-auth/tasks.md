## 1. Master kubelet trust anchor

- [x] 1.1 In `tasks/certs/ipa-pki-swap.yml`, after the apiServerOverride blockinfile task, add an `ansible.builtin.replace` patching `clientCAFile: /etc/kubernetes/pki/ca.crt` to the `ca-bundle.crt` path in `/var/lib/kubelet/config.yaml` (register result).
- [x] 1.2 Extend the existing conditional kubelet restart task gate with `or kubelet_client_ca_patch is changed`.

## 2. Worker kubelet trust anchor and auth blocks

- [x] 2.1 In `tasks/kube-install-join-node.yml`, fetch the `{{ ipa_kubeclusteradm_ca_name }}` CA from idm (`ipa ca-show`, same exception pattern as `kubernetes-ca`) and slurp it.
- [x] 2.2 Install `/etc/kubernetes/pki/ca-bundle.crt` (kubeclusteradm + kubernetes-ca) after the pki directory is created, and re-install it after `kubeadm reset` wipes pki (next to the `ca.crt` reinstall).
- [x] 2.3 Extend the minimal kubelet config copy task with the `authentication` (anonymous off, webhook on, x509 clientCAFile -> ca-bundle.crt) and `authorization` (mode: Webhook) blocks.

## 3. Verification

- [x] 3.1 Live-patched equivalent on the running molecule VMs (master + node1) and confirmed `kubectl logs`/`exec` no longer return 401; dikastes logs show "Successfully connected to Policy Sync server".
- [x] 3.2 Gate: `tcharl.servicemesh` change `upgrade-calico-istio-l7-integration` task 4.1 verify-monorepo green (exercises `kubectl exec` and `kubectl logs` cluster-wide).
- [x] 3.3 Follow-up (not blocking tonight): full `tcharl.ansible_orchestration` molecule cycle on the host-OS-matched scenario to regression-test the role edits from scratch.

## 4. Kubeadm self-signed CA retirement (post-swap disappearance, design D5)

- [x] 4.1 In `tasks/certs/ipa-certs.yml`, replace the "update controller-manager cluster-signing CA to retained kubeadm CA" task with an idempotent `replace` emptying `--cluster-signing-cert-file=` and `--cluster-signing-key-file=` in the KCM manifest (CSR signers disabled; regex stops matching once emptied).
- [x] 4.2 Gate the "backup kubeadm self-signed ca" copy on `ca.crt` still being the self-signed CA (read-only `community.crypto.x509_certificate_info` subject check) so post-swap re-converges neither re-create `ca.crt.kubeadm` nor flap changed.
- [x] 4.3 Make the gate anchor's `ca.crt.kubeadm` slurp conditional on the file existing (bundle-only anchor when absent), keeping the fresh-cluster old-cert window working and re-converges green.
- [x] 4.4 In `tasks/certs/ipa-pki-swap.yml`, after the post-swap gates pass, delete `/etc/kubernetes/pki/ca.crt.kubeadm`, `/etc/kubernetes/pki/ca.key` and `/tmp/kube-api-gate-anchor.crt` (`file: state: absent`).
- [x] 4.5 Extend `molecule/default/tests/test_master.py`: assert `ca.crt.kubeadm` and `ca.key` absent post-swap and the KCM manifest cluster-signing flags carry no kubeadm paths.
- [x] 4.6 Full molecule cycle on the host-OS-matched scenario (destroy → converge-monorepo → verify-monorepo → reconverge) — this also closes the still-open 3.3.
