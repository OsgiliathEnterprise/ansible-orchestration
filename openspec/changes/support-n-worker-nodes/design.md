## Context

See proposal.md for motivation. The role's task logic is already group-aware: `tasks/main.yml` guards every include on `kube_masters_group in group_names` / `kube_nodes_group in group_names`, and `drain-and-reset.yml` loops over `groups[kube_nodes_group]`. The single-worker assumption lives entirely in the molecule layer — `converge.yml` hosts lists, `prepare.yml` node-targeting plays, `molecule.yml` platform definitions, and `test_node.py`.

## Goals / Non-Goals

**Goals:**
- Prove the role converges ≥2 workers end-to-end (not just 1).
- Generalize the molecule layer so adding a worker is a one-line change.
- Parameterize tests across all workers.

**Non-Goals:**
- No changes to role task logic — it is already N-ready; this change verifies that, not rewrites it.
- No dynamic platform generation in molecule (molecule platforms are static per scenario).
- No multi-master / HA control-plane support (out of scope for worker scaling).

## Decisions

### D1: converge hosts = master + all workers via a union group
Target the play at a group that spans the master and every worker, so adding a worker is a one-line change rather than editing a comma-separated hostname list. Molecule platforms are static, so CI scenarios define a fixed small set (master + node1 + node2) while the role itself supports N.

- **Alternative considered:** pure enumeration (`hosts: master,node1,node2,…`). Rejected — brittle; every new worker requires editing the hosts line in all four scenario converge files.
- **Note:** if molecule's group generation makes a clean union group awkward, fall back to enumerating the defined workers (still driven by the platforms list, not a magic hostname).

### D2: prepare.yml node-targeting plays loop over the worker group
Convert the "NFS client on node" and "secure host" plays from a literal `node1` host list to a loop/hosts expression over the `kube_node` group, so every defined worker gets NFS-client + secure-host treatment.

### D3: tests parameterize across all workers
Derive `testinfra_hosts` from the inventory's worker hosts (all of `kube_node`) instead of the literal `["node1.osgiliath.test"]`, so node assertions run against every worker.

## Risks / Trade-offs

- [Molecule platforms are static, so CI cannot express "N workers" generically] → Accept a fixed small N in scenarios (≥2) to prove scaling; the role supports arbitrary N even though CI exercises 2.
- [Multiple workers joining against a shared control plane during one converge could contend] → The existing readiness gates (`/healthz` + profile availability) already serialize joins safely; no new contention handling needed.
- [Adding platforms increases scenario runtime/memory (each worker VM ~5120MB)] → Keep CI at 2 workers to bound resource use; document how to add more locally.

## Migration Plan

Additive and non-breaking: add a `node2` platform, extend the converge hosts expression, loop prepare plays, parameterize tests. Existing single-worker runs remain valid (a group with one member behaves as before). Rollback = revert the molecule-layer edits; role tasks are untouched.

## Open Questions

- How many workers should CI exercise? Defaulting to 2 for the primary scenario to bound VM memory/time — confirm acceptable, or keep some scenarios at 1 worker for a fast path.
