# PV NFS Kind (delta)

## MODIFIED Requirements

### Requirement: PV creation runs on first master node
The PersistentVolume creation tasks SHALL execute on the first Kubernetes master node, not on worker nodes. The `nfs_mountpoints` variable and associated task execution MUST be triggered when the host is in the master group. The apply SHALL be idempotent: when a PersistentVolume with the same name already exists and its rendered spec (NFS server, NFS path, capacity, access modes, storage class) matches the desired state, the tasks SHALL skip the delete and the apply entirely and report no change; the apply command MUST NOT suppress failures (`failed_when: false` is prohibited on it).

#### Scenario: Tasks run on master
- **WHEN** the role runs and the host is in `kube_masters_group`
- **THEN** the `nfs-mountpoints.yml` tasks execute
- **THEN** the PV manifest is rendered and applied via kubectl on that master

#### Scenario: Tasks do not run on worker nodes
- **WHEN** the role runs on a host in `kube_nodes_group` but NOT in `kube_masters_group`
- **THEN** the `nfs-mountpoints.yml` tasks do NOT execute

#### Scenario: Unchanged PV is not recreated
- **WHEN** the role converges and the named PV already exists with a spec matching the rendered manifest
- **THEN** no delete runs, no apply runs, and the PV tasks report no change

#### Scenario: Spec drift triggers re-apply
- **WHEN** the named PV exists but its spec differs from the rendered manifest (for example the NFS path or capacity changed)
- **THEN** the PV is deleted and re-applied so the cluster converges to the rendered spec

#### Scenario: Apply failure fails the converge
- **WHEN** the kubectl apply fails (API unreachable, invalid manifest)
- **THEN** the task fails and the converge stops at that task instead of continuing silently
