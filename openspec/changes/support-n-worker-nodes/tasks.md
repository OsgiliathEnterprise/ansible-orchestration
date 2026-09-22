## 1. Molecule layer generalization

- [ ] 1.1 Add a second worker platform (`node2.osgiliath.test`, group `kube_node`) to each scenario's `molecule/*/molecule.yml` and verify the platforms list contains ≥2 workers in every scenario.
- [ ] 1.2 Generalize `molecule/*/converge.yml` hosts from `master,node1` to master + all defined workers (union group, or enumerated from the platforms list) and verify the play targets every defined worker with no literal single-worker-only host list.
- [ ] 1.3 Convert `molecule/*/prepare.yml` node-targeting plays (NFS client, secure-host) from a literal `node1` host list to a loop over the `kube_node` group and verify no literal `node1` remains as a target in any `prepare.yml`.

## 2. Role verification (no code change expected)

- [ ] 2.1 Audit all `tasks/*.yml` for single-worker hardcoding and confirm every worker-facing operation is expressed against the `kube_node` group or per-host facts; record that no role task names a specific worker hostname as its target.

## 3. Tests

- [ ] 3.1 Parameterize `molecule/parallels/tests/test_node.py` so `testinfra_hosts` is derived from all inventory workers (not the literal `["node1.osgiliath.test"]`) and verify the node tests run against every worker host.

## 4. End-to-end verification

- [ ] 4.1 Run the full cycle on a ≥2-worker scenario (`destroy` → `converge-monorepo` → `verify-monorepo`) and verify both workers register as distinct `system:node:<hostname>` identities via `kubectl get nodes` and the cluster is healthy.
