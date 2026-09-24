## Why

The role's task logic is already group-aware (`main.yml` guards every include on `kube_masters_group` / `kube_nodes_group`, and `drain-and-reset.yml` loops over all nodes), but the molecule scenarios, prepare plays, and tests hardcode a single worker (`node1.osgiliath.test`). As a result an N-worker cluster is never actually exercised — we cannot prove the role converges more than one worker, which is the realistic case for any real cluster.

## What Changes

- Generalize the molecule layer from a hardcoded `node1` to a worker group: add a second worker platform and target all workers in converge/prepare instead of a literal hostname.
- Convert `prepare.yml` node-targeting plays (NFS client, secure-host) from a single `node1` host list to a loop over the `kube_node` group.
- Parameterize `tests/test_node.py` across every worker host rather than a fixed `["node1.osgiliath.test"]`.
- Audit role tasks to confirm no task hardcodes a specific worker (expected: none — all worker work is already group-driven).

## Capabilities

### New Capabilities
- `kube-worker-scaling`: the cluster converges an arbitrary number of worker nodes in a single pass; each worker joins independently and registers with its own per-node identity, and molecule scenarios + tests exercise at least two workers.

### Modified Capabilities
<!-- None: the role task logic is already group-aware; this change formalizes and extends the test/molecule layer to prove N-worker convergence without altering existing capability requirements. -->

## Impact

- `molecule/{default,default_noreset_kube,kvm,parallels}/converge.yml` — hosts list generalized from `master,node1` to master + all workers.
- `molecule/*/prepare.yml` — node-targeting plays loop over the worker group instead of a literal `node1`.
- `molecule/*/molecule.yml` — add a second worker platform (≥2 workers) so scenarios prove scaling.
- `molecule/parallels/tests/test_node.py` — parameterized across all worker hosts.
- Role tasks (`tasks/*.yml`) — verification only; no code change expected since the role is already group-driven.
