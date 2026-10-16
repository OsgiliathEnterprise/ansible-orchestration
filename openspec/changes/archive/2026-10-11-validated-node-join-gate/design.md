# Design

## Context

See proposal.md for motivation. The shape of the problem is a timeline asymmetry:

```
MASTER side (ipa-certs / ipa-pki-swap healthz polls)
  ca.crt on disk and API serving cert are in flux across restarts;
  during the swap window a single-CA anchor may not validate the
  serving cert → each gate anchors to the CA set expected at that
  phase: merged bundle (kubeadm + IPA) for the old-cert window,
  IPA CA only after the new-certificate gate.

NODE side (kube-install-join-node gate)
  master state is STABLE: ipa-certs.yml has fully completed, the API
  serves an IPA-CA-signed cert (client-ca = kubeadm+IPA bundle).
  The serving cert carries the master IP as a SAN (ipa-api-server.yml
  CSR subject_alt_name). The node simply lacks its trust anchor at
  gate time — because the CA fetch is ordered AFTER the gate.
```

So the node gate's `validate_certs: no` is an ordering artifact, not a constraint. The fix is reorder + validate.

## Goals / Non-Goals

**Goals:**
- Make the node-join readiness gate a TLS-validated check against the node's own IPA-derived trust anchor
- Fail fast (top of block, no node-local mutation) when the FreeIPA CA and the API's serving cert disagree
- Remove the `validate_certs: no` from `kube-install-join-node.yml`

**Non-Goals:**
- Changing the join block's skip condition, the per-node cert flow, the kubelet.conf construction, or the final `k8s_info` registration assertion
- Changing which address the gate polls (stays `orchestration_master_ip`)

## Decisions

**D1: Reorder the join block — FreeIPA-side gates first, then the validated API gate, then node-local mutation.**

New order inside the `when: not kube_node_joined` block:

```
1. profile gate   (delegate idm): kubernetes-ca + kubernetesNodes exist
2. fetch CA       (delegate idm) → slurp → /etc/kubernetes/pki/ca.crt
3. VALIDATED GATE (on node): uri https://<master_ip>:6443/healthz
                              ca_path: /etc/kubernetes/pki/ca.crt
4. systemd drop-in surgery, kubelet stop/kill, kubeadm reset (wipes /etc/kubernetes/pki), CA reinstall from the verified fetch, artifact cleanup
5. node cert request, kubelet.conf + config.yaml, kubelet start
6. k8s_info node-present assertion (unchanged)
```

Rationale:
- Steps 1-2 have no dependency on any node-local state (they run on the idm host / are a plain copy onto the node), so hoisting them is safe.
- The profile gate must precede the CA fetch: `ipa ca-show kubernetes-ca` 404s if the CA doesn't exist, and the CA is created before the profile, so passing the profile gate (`until: stdout == '1'`) guarantees the fetch can succeed. No new retry needed on the fetch.
- Bonus side effect: today, a profile-gate failure happens *after* the node's kubelet has already been stopped and drop-ins rewritten. With FreeIPA-side gates first, the node's local state is left completely untouched until both external readiness signals pass — a cleaner failure mode for `rescue`.

**D2: Validated gate via `uri` module `ca_path`, polled over the master IP.**

```yaml
- name: Kube-install-join | wait for API server readiness (validated)
  ansible.builtin.uri:
    url: "https://{{ orchestration_master_ip }}:6443/healthz"
    ca_path: /etc/kubernetes/pki/ca.crt
    status_code: 200
  become: true
  retries: 40
  delay: 5
  register: api_server_ready
  until: api_server_ready.status == 200
```

Rationale:
- `ca_path` (the `uri` module's CA-anchor parameter in ansible-core 2.21; it accepts a PEM file and is passed as the SSL context's CAfile) points at the anchor the node itself fetched from FreeIPA — the gate now asserts "the API serves a cert chaining to the CA I am about to commit to kubelet.conf", exactly the invariant the deferred-join design exists to protect.
- Polling the master IP (not the hostname) is deliberate: the serving cert carries `IP:{{ orchestration_master_ip }}` as a SAN (`ipa-api-server.yml` CSR), and the node's `kubelet.conf` will connect to that same IP — the gate validates the exact endpoint the kubelet will use, without introducing a node-side DNS dependency.
- `validate_certs: no` is removed, not kept alongside `ca_path` (they conflict).
- Retry semantics: `until`/`retries` retry on module exceptions too, so a TLS verification failure during an in-progress API restart recovers; a persistent mismatch fails after the same 40×5s budget as today's liveness gate, but with an informative TLS error at the top of the block instead of a `rescue` journalctl dump at the end.

**D3: Update the file header comment (design D2/D3 statement).**

Readiness signal 1 changes from "the API server is reachable (`/healthz == 200`)" to "the API server is reachable and its serving certificate validates against the node's IPA-derived trust anchor". Signal 2 (profile + CA exist in FreeIPA) is unchanged but now explicitly precedes the CA fetch.

**D4: Master-side healthz polls become per-phase validated gates (`ipa-pki-bootstrap` spec delta).**

The three master-side healthz polls are converted from liveness-only to TLS-validated, each anchored to the CA set expected at that phase (per the `ipa-pki-bootstrap` spec delta):
- Old-cert window gate (`ipa-certs.yml`, after static pod restart with new kubeconfig/manifests): anchor = merged bundle `ca-bundle.crt` — passes whether the API presents the old (kubeadm) or the new (IPA) serving cert.
- New-certificate gate (`ipa-certs.yml`) and post-swap stabilization gate (`ipa-pki-swap.yml`): anchor = IPA CA `ca.crt` — passes only when the running server presents the IPA-signed serving cert.

All use `uri` with `ca_path` (the module's CA-anchor parameter in ansible-core 2.21; it accepts a PEM file and is passed as the SSL context's CAfile) plus the same `until: <reg> is not skipped and <reg>.status | default(0) == 200` guard as D2, so a TLS verification failure during an in-progress restart is retried instead of failing immediately.

**Alternatives considered:**

- **Keep task order, add a separate trust probe after CA install** — rejected: when trust is broken, the node has already spent the FreeIPA cert request before discovering it; a single validated gate at the top is simpler and fails earlier.
- **Document the liveness-only check and keep `validate_certs: no`** — rejected: per-phase anchoring (merged bundle during swap windows, D4) makes validated gates correct even while the serving cert is in flux, so liveness-only loses fail-fast everywhere without buying anything.
- **Poll the master hostname instead of the IP** — rejected: adds a node-side DNS dependency to the gate and validates a different endpoint than the one `kubelet.conf` will use.

## Risks / Trade-offs

- [Persistent CA drift burns the full 40×5s gate budget before failing] → acceptable: same budget as today's equivalent failure at the `k8s_info` step, and the error is now a clear TLS verification failure at the top of the block instead of a 2000-line journalctl dump.
- [Hoisting the CA fetch runs kinit + `ipa ca-show` on the idm host earlier than today] → harmless: kinit is idempotent, and the delegated fetch is read-only (`ipa ca-show`); no new failure mode — if the idm host is unreachable, today's profile gate would have failed the same way.
- [Python `ssl` host-matching for IP SANs] → supported (Python 3.7+ `ssl` handles IP addresses in server_hostname); the serving cert's IP SAN makes this a non-issue in practice.
- [Trade-off] The node's `/etc/kubernetes/pki/ca.crt` is now installed slightly earlier than today (before kubelet stop) → no behavior change: nothing between the old and new positions reads that file.
- [`kubeadm reset` wipes `/etc/kubernetes/pki/*`, including the freshly installed trust anchor — discovered during verification: without a reinstall, kubelet crash-loops on a missing `certificate-authority`] → the anchor is reinstalled from the already-verified slurped content immediately after the reset (byte-identical to what passed the content-match gate), so kubelet always starts with a valid `ca.crt` present.

## Migration Plan

Single-file change to `tasks/kube-install-join-node.yml` (reorder + gate parameters + header comment); no state, variable, or inventory migration. Verify with `converge-monorepo` + `verify-monorepo` (parallels scenario): the node must join through the validated gate on a fresh converge. Rollback: revert the file (no persisted state is introduced).

## Open Questions

None.
