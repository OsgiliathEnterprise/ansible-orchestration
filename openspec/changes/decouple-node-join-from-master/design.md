## Context

See proposal.md for motivation. Current state that shapes this design:

- `molecule/*/converge.yml` runs **two sequential plays** — master fully (init + IPA cert swap), then node (packages + join). The node play's join (`tasks/kube-install-join-node.yml`) slurps `ca.crt`, `admin.conf`, and the admin client cert/key off the master, so every worker shares the master's admin identity.
- The FreeIPA `kubernetes-ca` is created during the master's converge (`tasks/ipa-kubernetes-ca.yml`, delegated to the IDM host). It depends only on **IPA being up + deterministic IP values** (service CIDR, master IP) — *not* on `kubeadm init`.
- Worker nodes are already IPA-enrolled clients with keytabs (`tcharl.ansible_securehost` enrolls `idm_client_group`), so per-node `ipacert` requests are possible without new enrollment work.
- **Constraint (user):** the `kubernetes-ca` creation stays inside the orchestration role — it is *not* moved into `prepare.yml`.

## Goals / Non-Goals

**Goals:**
- Each worker carries its own least-privilege identity (`system:node:<host>` in group `system:nodes`) sourced from IPA.
- Convergence is order-tolerant: one pass across master + workers; only the join step waits for API-server readiness.
- A worker's trust anchor and client cert come from IPA, not copied off the master.

**Non-Goals:**
- No change to master-side PKI bootstrap (`ipa-pki-bootstrap` behavior is untouched).
- Do **not** move `kubernetes-ca` creation into `prepare.yml`.
- Do **not** rework kubeadm discovery-token / CSR bootstrap (it is broken by the CA swap; we bypass it, as today).
- No signing sidecar on the IDM host.

## Decisions

### D1 — Per-node cert via a new `kubernetesNodes` profile
Each worker requests its own certificate with `O=system:nodes`, `CN=system:node:<hostname>`. A kubelet only registers and gets node-scoped RBAC under that exact subject (K8s maps it to user `system:node:<host>` in group `system:nodes`). The existing `kubeAdministrators` profile hardcodes `O=system:masters`, so a new profile is required.
- *Alternative rejected:* reuse the master's admin cert (`O=system:masters`) — this just relocates today's shared-admin smell onto a per-node file and defeats the purpose.
- **Subject assembly — CSR carries hostname, profile adds the prefix (validated):** IPA requires a host-principal cert request's subject CN to match the principal name (`host/<hostname>`). A CSR carrying `CN=system:node:<hostname>` is therefore rejected at request time with *"hostname in subject of request ... does not match name or aliases of principal 'host/<h>'"*. The split that works: the **CSR carries `CN=<hostname>` + `O=system:nodes`** (passes the host check), and the **`kubernetesNodes` profile template adds the prefix** — `policyset.serverCertSet.1.default.params.name=CN=system:node:$request.req_subject_name.cn$, O=system:nodes` — so the *issued* cert is exactly `CN=system:node:<hostname>, O=system:nodes`. Validated end-to-end on the parallels VM (matching-CN CSR requested via `ipa cert-request --profile-id=kubernetesNodes --ca=kubernetes-ca --principal=host/<h>` → issued subject as required). Mirrors how the master's `kubeAdministrators` cert already works.

### D2 — Node trust anchor sourced from IPA, not copied from master
The worker fetches `ca.crt` via `ipa ca-show kubernetes-ca` (delegated to the IDM host) instead of slurping it off the master. The CA is an IPA artifact, not a master post-processing artifact; this removes the last master-file dependency in the join path.

### D3 — Join gated on readiness + CA existence, *not* hoisting or fixed play order
The join step waits for **both** `https://<api>:6443/healthz == 200` **and** `kubernetes-ca` present in FreeIPA. This makes ordering irrelevant without moving any task: the gate subsumes "CA exists" and "apiserver up."
- *Alternative considered:* hoist `ipa-kubernetes-ca.yml` to the top of converge so parallel cert requests never race CA creation. Rejected as unnecessary — the D3 gate already covers the race, and it keeps CA creation in its current location (honoring the user constraint). Hoisting is noted as an optional future enhancement if cert-request latency becomes a concern.

### D4 — Single-pass, order-tolerant converge
Replace the two sequential plays with one pass over all kube hosts. The role already branches per group via `when: <group> in group_names`, so each host runs only its own branch; node prep (packages/CRI/firewall/NFS) is independent of master and runs concurrently. Only the join task carries a cross-host dependency, satisfied by the D3 gate.
- *Alternative rejected:* keep two plays but reorder — still encodes a fixed sequence, which is exactly what we are removing.

### D5 — Keep "bypass bootstrap"; issue the node cert directly
Nodes do not run `kubeadm join` / CSR bootstrap (broken by the CA swap). Instead each worker gets a pre-issued IPA client cert and a locally-constructed `kubelet.conf` (own cert/key + IPA CA + deterministic server URL from `orchestration_master_ip`). This sidesteps the JWS/bootstrap breakage that originally motivated the copy-admin-cert hack.

### D6 — Per-node `kubelet.conf` constructed, not copied
The worker's `/etc/kubernetes/kubelet.conf` is generated from its own cert/key + IPA CA + `https://<master>:6443`, replacing the current "copy master's `admin.conf`" step. The systemd drop-in and kubelet start logic in `kube-install-join-node.yml` are retained; the join *verification* step is re-pointed per D7 (it was previously left on master `admin.conf`).

### D7 — Join verification uses the node's own identity, not master `admin.conf`
The "wait for node to appear" step originally ran `kubectl get node <host> --kubeconfig /etc/kubernetes/admin.conf` **delegated to the master**. In single-pass converge this breaks: by join time the API server already serves IPA-signed certs, but the master's `admin.conf` is only re-pointed at the IPA CA in `ipa-pki-swap`, which runs *after* join — so the check fails every attempt with `x509: certificate signed by unknown authority`. The fix verifies from **the node itself** using its own `/etc/kubernetes/kubelet.conf`: `kubectl get node <host> --kubeconfig /etc/kubernetes/kubelet.conf` run on the worker. This is consistent with D2/D6 and the spec's node-scoped-identity intent, and removes the last master-post-processing dependency from the join path.
- *Alternative rejected (B):* reorder `ipa-pki-swap` before join — re-introduces the master→node sequencing this change exists to remove.
- *Alternative rejected (C):* drop the API-side check and trust local kubelet logs — less authoritative than confirming the Node object exists in etcd.
- **RBAC caveat:** `system:node:<hostname>` must be able to `get` its own Node object; task 1.3 validates this before relying on it (fall back to a node-scoped read the cert does permit if not).

## Risks / Trade-offs

- [RBAC subject wrong → node fails to register or gets excessive privileges] → Validate with a throwaway spike on one worker *before* restructuring converge: confirm an IPA cert with `O=system:nodes`/`CN=system:node:<host>` lets the kubelet register and pass RBAC. Assert it in `test_node.py`.
- [Naive CSR carrying `CN=system:node:<h>` rejected at request time by IPA's host-principal check] → D1 subject-assembly split (CSR carries hostname; profile adds the prefix); validated end-to-end on parallels before restructuring converge.
- [Parallel per-node cert request races CA creation] → D3 gate requires `kubernetes-ca` to exist before the request proceeds.
- [Single-play fact gathering needs master NIC facts for `orchestration_master_ip`] → Facts are gathered at play start across all hosts; both VMs are up by converge (prepare creates them). Verify no "master not ready" edge in a merged play.
- [Join verification via master `admin.conf` fails with TLS unknown authority in single-pass — admin.conf is re-pointed only by the later `ipa-pki-swap`] → D7 verifies from the node's own identity; validated end-to-end on parallels (task 4.4).
- [Per-node cert expiry/renewal now per-host rather than one shared cert] → Out of scope for this change; note that each node's cert carries its own validity, same as today's shared cert.
- [Re-converge idempotency] → Guard the per-node cert request by `stat` (mirrors the master pattern); join skips when `/etc/kubernetes/kubelet.conf` already exists.
- [Actual wall-clock win depends on parallelism] → Ensure enough Ansible forks and that node-prep tasks are genuinely independent of master; measure before/after converge time.

## Migration Plan

1. **Additive first:** introduce the `kubernetesNodes` profile + per-node cert task without touching the existing (master) flow or the old join path — nothing breaks while both coexist.
2. **Validate** the RBAC subject on one worker (spike).
3. **Switch the join mechanism** in `kube-install-join-node.yml` to D5/D6; keep the old copy-from-master path behind a variable until validated, then remove it.
4. **Convert converge** scenarios from two plays to the single-pass form with the D3 gate (pilot on `parallels`, then `default`/`kvm`).
- **Rollback:** revert `converge.yml` to two plays and re-enable the old join path via the variable; the new profile/task are additive and harmless if unused.

## Open Questions

- Per-node certificate validity/TTL and any renewal strategy (a parameter, not a mechanism change).
- Rollout sequencing: apply single-pass converge to all molecule scenarios at once vs. pilot on `parallels` first (a rollout choice, not an approach change).
