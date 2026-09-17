## Context

The PV template (`templates/persistent-volume.yml.j2`) currently uses `kind: PersistentVolume` with a `local:` volume source pointing to a node-local mount path. The NFS share is first mounted on the worker via the NFS client role, then exposed through Kubernetes as a local PV. In `tasks/main.yml`, the NFS mountpoint tasks are gated by `kube_nodes_group in group_names` (line 79), so they run on workers — but should run on the master since kubectl commands delegate to `groups['kube_master'] | first`. The `nfs_mountpoints` variable is only passed to worker nodes in converge.yml.

See `proposal.md` for motivation.

## Goals / Non-Goals

**Goals:**
- Replace `local:` volume source with `nfs:` in the PV template
- Move PV creation execution from workers to the first master node
- Pass `nfs_mountpoints` variable on the master converge play (not only on nodes)
- Update main.yml gating condition from `kube_nodes_group` to `kube_masters_group`
- Update storage class name to reflect NFS backing
- Ensure tests validate the new PV structure

**Non-Goals:**
- Migrating to a CSI driver (tracked as separate TODO)
- Changing how NFS exports are created on the server side
- Modifying the NFS client role or mountpoint configuration logic

## Decisions

### Decision: Use `spec.nfs` directly instead of keeping local mount for PV access
The Kubernetes NFS volume type mounts the share directly when a pod binds to the PV. This removes the requirement that every worker node has the NFS export pre-mounted via the system mount manager. The NFS client role's mount can be removed from the converge flow if it was only serving this purpose, but we'll leave it in place for now to avoid breaking other dependencies.

### Decision: Run PV tasks on master instead of workers
The `persistent-volume.yml` already delegates kubectl operations to `groups['kube_master'] | first`. Running the entire task chain on the master avoids unnecessary delegation and is more consistent with how all other kubectl-based tasks (kubeadm init, admin-user, etc.) are gated by `kube_masters_group in group_names`.

### Decision: Derive server and path from existing variables
The `nfs_mountpoints` structure already carries the necessary information:
- `host` → `spec.nfs.server`
- `remote + subtree` → `spec.nfs.path`

No new variables are needed. The template will use `nfs_mountpoint.host` for the server and `nfs_mountpoint.remote + kube_volume_to_mount.subtree` for the path.

### Decision: Rename storage class to `nfs-storage`
The existing `local-storage` class name is misleading for an NFS-backed volume. Updating to `nfs-storage` makes the backing type explicit and avoids confusion with Kubernetes Local PersistentVolumes.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Existing PVs of type `local:` will conflict — re-running may fail since kubectl cannot change a PV's volume source in-place | Implementation should delete the old PV before creating the new one, or use `kubectl replace --force` |
| Pods with bound PVCs will lose access during migration | This is a dev/test environment; no production workloads are affected |

## Migration Plan

1. On next converge run, the existing local-type PV will be deleted (if it exists) before applying the new NFS-type PV
2. The `persistent-volume.yml` task handles this by cleaning up stale state
3. Rollback: revert the template change and re-run converge to recreate the local-type PV
