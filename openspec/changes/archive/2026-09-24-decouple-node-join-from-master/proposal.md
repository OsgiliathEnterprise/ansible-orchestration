## Why

Because the role sources its PKI from FreeIPA, worker nodes can only join after the master has finished *all* IPA post-processing: `kube-install-join-node.yml` slurps `ca.crt`, `admin.conf`, and the admin client cert/key off the master. This forces a strict two-play master→node sequence in every converge scenario and gives **every** worker node the same shared admin identity (the master's `kubeadm.crt`). It also makes it impossible to add a node later without the master present in the play. We want convergence that is order-tolerant — each worker carries its own least-privilege identity sourced directly from IPA, and only the final join step waits for the API server.

## What Changes

- **Per-node client certificate (B):** each worker requests its *own* certificate from the `kubernetes-ca` with subject `O=system:nodes`, `CN=system:node:<hostname>`, instead of reusing the master's admin cert. This is the identity a kubelet needs to register and get node-scoped RBAC.
- **New FreeIPA profile:** a `kubernetesNodes` certificate profile (`O=system:nodes`) is created alongside the existing `kubeAdministrators` (`O=system:masters`).
- **Node trust anchor from IPA (B):** a worker obtains its CA (`/etc/kubernetes/pki/ca.crt`) directly from the IPA `kubernetes-ca`, not copied off the master.
- **Readiness-gated, order-tolerant join (C):** node join waits for API-server readiness (`/healthz` 200) and `kubernetes-ca` availability rather than a fixed play order; node prep (packages/CRI/firewall/NFS) runs without depending on master post-processing.
- **Single-pass converge (C):** scenarios no longer require two sequential plays (master fully, then node); hosts converge in one order-tolerant pass where only the join is gated.
- **Removal:** the copy-from-master join path (`admin.conf` → `kubelet.conf`, plus `kubeadm.crt`/`kubeadm.pem`) is removed from worker nodes.
- **Decoupled join verification:** confirming a worker registered uses the node's own per-node identity (its local `kubelet.conf`) rather than master `admin.conf`, so it succeeds before the master's PKI swap (`ipa-pki-swap`) runs.

## Capabilities

### New Capabilities
- `kube-node-join`: how a worker node obtains its per-node IPA identity and joins the cluster, decoupled from master post-processing state — per-node `O=system:nodes` certificate, trust anchor fetched from IPA, readiness-gated join, order-tolerant convergence.

### Modified Capabilities
- `ipa-pki-infra`: add a requirement that a `kubernetesNodes` certificate profile (`O=system:nodes`) is created and linked to the `kubernetes-ca`, alongside the existing `kubeAdministrators` profile.

## Impact

- `tasks/kube-install-join-node.yml` — rewritten: request per-node cert + fetch CA from IPA, drop the admin.conf/admin-cert copy-from-master path; re-point join verification to the node's own identity (no master delegation).
- New task file (e.g. `tasks/kube-node-cert.yml`) — per-node CSR + `ipacert` request with the `kubernetesNodes` profile.
- `tasks/ipa-kubernetes-ca.yml` / infra tasks — create and link the `kubernetesNodes` profile.
- `molecule/*/converge.yml` (parallels, default, kvm) — replace two sequential plays with one order-tolerant pass; add an API-server readiness gate before join.
- `molecule/default/tests/test_node.py` — extend to assert per-node identity (`O=system:nodes`) and that workers do not share the master's admin credentials.
- No change to master-side PKI bootstrap behavior (`ipa-pki-bootstrap`).
