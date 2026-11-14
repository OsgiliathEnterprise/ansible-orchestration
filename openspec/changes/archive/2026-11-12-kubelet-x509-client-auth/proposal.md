## Why

After the IPA PKI swap, the API server's `apiserver-kubelet-client` certificate is re-issued under CA #2 (`kubeclusteradm`), but the kubelets only trust CA #1 (`kubernetes-ca`): the master's kubeadm-generated kubelet config pins `authentication.x509.clientCAFile: /etc/kubernetes/pki/ca.crt`, and the worker's hand-crafted minimal kubelet config (`kube-install-join-node.yml`) has **no `authentication`/`authorization` blocks at all**. Every API-server-proxied subresource — `kubectl exec`, `kubectl logs`, `kubectl port-forward` — is therefore rejected by the kubelet with `401 Unauthorized` (`error: unable to upgrade connection: Unauthorized` / `You must be logged in to the server ( pods/log ...)`). This surfaced while gating `tcharl.servicemesh` change `upgrade-calico-istio-l7-integration` task 4.1: its verify test needs `kubectl exec` (ALP client curl) and `kubectl logs` (dikastes "Successfully connected to Policy Sync server").

Beyond closing the 401, the post-swap trust surface must be exactly the two IPA-issued CAs: the kubeadm **self-signed CA must fully disappear from the master once the swap completes** — no retained cert/key files, no CSR signing under it, no trust anchor left behind (it currently survives via KCM's `--cluster-signing-*-file` pair, the on-disk `ca.crt.kubeadm`/`ca.key`, and the transient `/tmp` gate anchor).

## What Changes

- **Master** (`tasks/certs/ipa-pki-swap.yml`): immediately after the kubelet apiServerOverride blockinfile (the only point where `/var/lib/kubelet/config.yaml` provably exists), patch `/var/lib/kubelet/config.yaml` so `clientCAFile` points at `ca-bundle.crt` instead of `ca.crt` (idempotent `replace`), and restart kubelet only when the patch changed the file.
- **Worker** (`tasks/kube-install-join-node.yml`): fetch and install the `kubeclusteradm` CA (delegated to idm, same pattern as `kubernetes-ca`) as `/etc/kubernetes/pki/ca-bundle.crt` (CA #2 + CA #1), reinstalled after `kubeadm reset` wipes the pki directory; extend the minimal kubelet config with `authentication` (`anonymous: disabled`, `webhook: enabled`, `x509.clientCAFile: /etc/kubernetes/pki/ca-bundle.crt`) and `authorization` (`mode: Webhook`) blocks.
- **Master — retire the kubeadm self-signed CA** (`tasks/certs/ipa-certs.yml`): empty KCM's `--cluster-signing-cert-file` / `--cluster-signing-key-file` instead of re-pointing them at the retained kubeadm CA (CSR signers have zero consumers: bootstrap/rotation already removed, all issuance via IPA `ipacert`); gate the kubeadm-CA backup task so post-swap re-converges neither re-create `ca.crt.kubeadm` nor flap; make the gate anchor's kubeadm-CA slurp conditional on the retained file existing.
- **Master — artifact removal** (`tasks/certs/ipa-pki-swap.yml`): after the post-swap gates pass, delete `ca.crt.kubeadm`, the kubeadm private key `ca.key`, and the transient `/tmp/kube-api-gate-anchor.crt`.

## Capabilities

### New Capabilities

(None.)

### Modified Capabilities

- `kube-node-join`: the worker's kubelet must authenticate API-server-proxied requests via x509 client certificates chained to the IPA-issued CA bundle, and authorize via Webhook.
- `ipa-pki-bootstrap`: the master's kubelet x509 client authentication must trust the merged CA bundle so the API server's kubelet-client certificate (re-issued under CA #2) validates; and the kubeadm self-signed CA must be fully retired after the swap — its files, cluster signing and trust anchors gone, with transient mid-swap trust allowed only for the fresh-cluster old-cert window.

## Impact

- `tasks/certs/ipa-pki-swap.yml` — one new `replace` task (clientCAFile -> ca-bundle.crt); the existing conditional kubelet restart also gated on it; end-of-swap removal of `ca.crt.kubeadm`, `ca.key` and the `/tmp` gate anchor.
- `tasks/kube-install-join-node.yml` — two new fetch/slurp tasks, two new install tasks, extended minimal kubelet config content.
- `tasks/certs/ipa-certs.yml` — KCM cluster-signing flags emptied (replacing the re-point-to-kubeadm-CA task); backup task gated on the self-signed CA still being present; gate-anchor slurp made conditional on the retained file.
- `molecule/default/tests/test_master.py` — new assertions: `ca.crt.kubeadm`/`ca.key` absent post-swap, KCM manifest cluster-signing flags carry no kubeadm paths.
- No interface or variable changes; converge behavior preserved. Fixes cluster-wide `kubectl exec`/`logs`/`port-forward` after the PKI swap.
