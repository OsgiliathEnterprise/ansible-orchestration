## Context

The API server authenticates to kubelets with `--kubelet-client-certificate=/etc/kubernetes/pki/apiserver-kubelet-client.crt`. After the CA swap this cert is minted under CA #2 (`kubeclusteradm`), but kubelet x509 client auth on the master still trusts only `ca.crt` (CA #1 `kubernetes-ca`), and the worker's minimal kubelet config enables no authenticator at all. Kubelet then answers proxied subresource requests with 401.

## Decisions

### D1 — Trust bundle, not a swap

Point `clientCAFile` at the merged bundle (`ca-bundle.crt`: CA #1 + CA #2, already built by `ipa-certs.yml` on master; same content built on workers) rather than only CA #2. The bundle is exactly the two IPA-issued CAs the control plane itself trusts via `--client-ca-file` / `--root-ca-file`, so the kubelet's client-auth surface mirrors the API server's; CA #2 signs the `apiserver-kubelet-client` cert, CA #1 stays in for symmetry with that surface and because both are renewed together under IPA. Both CAs chain to the IPA root; only the two cluster CAs are added, not the full IPA CA set, keeping the trust surface minimal. The kubeadm self-signed CA belongs to no trust surface at all — it is retired outright (D5).

### D2 — Master: patch in `ipa-pki-swap.yml` next to the existing kubelet patch

The patch runs in `ipa-pki-swap.yml`, right after the `Ipa-pki-swap | add API server override block to kubelet config` blockinfile — the first point where the kubeadm-generated `/var/lib/kubelet/config.yaml` provably exists (patching earlier, in `ipa-certs.yml`, would fail on fresh VMs where the file is not yet created). It reuses the existing conditional restart task: `when: kubelet_config_override is changed or kubelet_client_ca_patch is changed`. On re-converge both registers are unchanged, so kubelet is not churned (idempotence preserved).

### D3 — Worker: install the bundle alongside `ca.crt`

`kube-install-join-node.yml` fetches the second CA from idm with the same shell exception used for `kubernetes-ca` (`ipa ca-show ... --certificate-out`), slurps it, and writes `ca-bundle.crt` = kubeclusteradm + kubernetes-ca PEMs. The copy tasks are content-idempotent. The install is duplicated after `kubeadm reset` (which wipes `/etc/kubernetes/pki/`) exactly like the existing `ca.crt` reinstall. `kubelet.conf` keeps pointing at `ca.crt` (that validates the *serving* cert — CA #1 — unchanged behavior).

### D4 — Worker kubelet config gains the standard auth blocks

The minimal config gains:

```yaml
authentication:
  anonymous:
    enabled: false
  webhook:
    enabled: true
  x509:
    clientCAFile: /etc/kubernetes/pki/ca-bundle.crt
authorization:
  mode: Webhook
```

`webhook`/`Webhook` delegate node-identity authz to the API server (SubjectAccessReview), matching kubeadm defaults. Anonymous stays disabled. The copy task is content-idempotent; kubelet starts with the blocks in place (config is written before the join flow starts kubelet), so no restart task is needed on workers.

### D5 — Retire the kubeadm self-signed CA after the swap

After the swap, the kubeadm self-signed CA survives only in three vestigial places on the master, none of which has a real consumer: (a) kube-controller-manager signs CSRs via `--cluster-signing-cert-file=…/ca.crt.kubeadm` + the untouched `--cluster-signing-key-file=…/ca.key` — but this role mints every certificate through IPA `ipacert` enrollment, the master's bootstrap drop-in and cert rotation are already removed (`kube-apiserver-kubelet-client.yml`) and workers never had them, so the CSR signers have zero consumers; (b) the retained files `ca.crt.kubeadm` and the kubeadm private key `ca.key` on disk; (c) the mid-swap gate anchor `/tmp/kube-api-gate-anchor.crt` (kubeadm CA + bundle), needed only for the fresh-cluster old-cert window while the API still presents the kubeadm-signed serving cert. Decisions:

- **Empty the cluster-signing flags.** Replace the "update controller-manager cluster-signing CA to retained kubeadm CA" task in `ipa-certs.yml` with an idempotent `replace` that empties both `--cluster-signing-cert-file=` / `--cluster-signing-key-file=` values in the KCM manifest (empty ⇒ those CSR signers stay disabled; the per-signer flags are unset and fall back to the empty pair). Once emptied the regex no longer matches, so re-converges are no-ops.
- **Gate the backup task.** The existing "backup kubeadm self-signed ca" copy is gated on `ca.crt` still being the self-signed CA (read-only `community.crypto.x509_certificate_info` subject check): post-swap `ca.crt` holds the IPA CA #1, so an ungated backup would re-create `ca.crt.kubeadm` from the IPA cert on every re-converge and the file would never disappear (and would flap changed every run).
- **Conditional gate anchor.** The anchor's `ca.crt.kubeadm` slurp is conditional on the file existing: fresh converge gets the full three-CA anchor (old-cert window), re-converge builds a bundle-only anchor.
- **Delete at end of swap.** After the post-swap gates pass, `ipa-pki-swap.yml` deletes `/etc/kubernetes/pki/ca.crt.kubeadm`, `/etc/kubernetes/pki/ca.key` and `/tmp/kube-api-gate-anchor.crt` with `file: state: absent` (idempotent; deleting after the gates keeps the transient old-cert window working).

The transient trust is allowed mid-swap only: the end state has no kubeadm-CA file, key, signer or trust anchor anywhere on the master. The separate kubeadm `front-proxy-ca` (aggregation-layer trust) is explicitly out of scope for this change.

## Risks / Trade-offs

- Kubelet restart on the master interrupts port-forwarded sessions briefly; static pods are unaffected and pods on the master resync on reconnect. Occurs only on the first converge after the fix.
- If a deployment ever runs kubelet with `/var/lib/kubelet/config.yaml` absent, the `replace` fails loudly rather than silently skipping — acceptable: this role owns that file's lifecycle.
- With the CSR signers disabled (and `ca.key` deleted, irreversibly), any workflow that re-introduces TLS bootstrap or relies on `kubeadm` cert lifecycle produces CSRs that are never signed (the kubelet would go Unauthorized) until the role re-converges and re-empties the flags. `kubeadm upgrade` is the realistic trigger: it rewrites the KCM manifest flags back to `ca.crt`/`ca.key`, and with `ca.key` gone the KCM static pod crash-loops until the role's `replace` tasks restore the disabled state.
- Retiring the signers assumes the zero-consumer analysis holds: if a future feature needs CSR-based issuance (TLS bootstrap, serving-cert signer, an aggregated API using kubelet client certs), the retirement must be revisited — the issuance path would have to move to an IPA profile, not back to a self-signed CA.
