# Proposal

## Why

The node-join readiness gate (`tasks/kube-install-join-node.yml`, "wait for API server readiness") polls `https://<master_ip>:6443/healthz` with `validate_certs: no` — a pure liveness check. This is an ordering artifact, not a necessity: the gate runs before the node fetches its trust anchor, but by join time the master's TLS state is already stable (`ipa-certs.yml` has completed) and the API serving certificate carries the master IP as a SAN. Consequence: if the FreeIPA `kubernetes-ca` has drifted from what the API actually serves (e.g. master re-initialized in a partial re-run), the mismatch is only discovered at the final `k8s_info` step — after drop-in surgery, `kubeadm reset`, and a kubelet restart — producing a long, noisy failure (the `rescue` block dumps 2000 lines of journalctl) instead of a clear, early TLS error at the top of the block.

## What Changes

- Reorder `tasks/kube-install-join-node.yml`: move the FreeIPA `kubernetesNodes` profile gate and the CA fetch + install on the node to the top of the join block, ahead of the API readiness gate (the profile gate must precede the CA fetch: the CA exists before the profile, so passing the profile gate guarantees the fetch succeeds).
- Replace the liveness-only readiness gate (`validate_certs: no`) with a TLS-validated `uri` poll using `ca_certificate: /etc/kubernetes/pki/ca.crt`. The gate now passes only when the API is reachable **and** serves a certificate chaining to the very CA the node is about to bake into `/etc/kubernetes/kubelet.conf`.
- Update the file's header comment (design D2/D3 statement): readiness signal 1 changes from "API server is reachable" to "API server is reachable and trust-verifiable against the node's own IPA-derived CA".
- The four master-side `validate_certs: no` healthz polls (`ipa-certs.yml`, `ipa-pki-swap.yml`) are **out of scope and unchanged**: during CA-swap windows neither the old nor the new CA is the correct trust anchor, so liveness-only is the only correct check there; TLS trust is asserted there by the subsequent `openssl verify` / `kubectl` tasks.
- No behavior change for already-joined re-runs: the join block is skipped exactly as before when `/etc/kubernetes/kubelet.conf` exists.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `kube-node-join`: the "Node join waits for API server readiness" requirement changes from a liveness-only healthz gate to a TLS-validated gate verified against the node's own IPA-derived trust anchor; the trust anchor is fetched from FreeIPA *before* the gate so the gate can assert it.

## Impact

- `tasks/kube-install-join-node.yml` — task reordering, gate parameter change (`validate_certs: no` → `ca_certificate`), header comment update.
- `openspec/specs/kube-node-join/spec.md` — readiness-gate requirement and scenario text.
- No variable, default, module, or inventory changes. No changes to `ipa-certs.yml`, `ipa-pki-swap.yml`, or any master-side task file.
- Verification: `converge-monorepo` + `verify-monorepo` (parallels scenario) — the node joins through the validated gate; a deliberately mismatched CA would fail at the gate with a TLS error instead of at the final `k8s_info` step.
