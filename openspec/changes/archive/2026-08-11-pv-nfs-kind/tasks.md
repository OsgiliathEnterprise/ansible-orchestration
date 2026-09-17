## 1. Move PV task execution to master node

- [ ] 1.1 Change `tasks/main.yml` line 79 condition from `kube_nodes_group in group_names` to `kube_masters_group in group_names`
- [ ] 1.2 Add `nfs_mountpoints` variable to the master converge play in `molecule/parallels/converge.yml` (and other scenario converge files)

## 2. Update NFS server propagation and template

- [ ] 2.1 Modify `tasks/nfs-mountpoints.yml` to propagate the parent `host` field into each mountpoint so it's available as `nfs_mountpoint.nfs_server` during template rendering
- [ ] 2.2 Replace `spec.local` block in `templates/persistent-volume.yml.j2` with `spec.nfs.server` and `spec.nfs.path`
- [ ] 2.3 Set `spec.nfs.server` to `{{ nfs_mountpoint.nfs_server }}`
- [ ] 2.4 Set `spec.nfs.path` to `{{ nfs_mountpoint.remote + (kube_volume_to_mount.subtree | default('')) }}`
- [ ] 2.5 Update `metadata.name` to derive from NFS path instead of local mount path
- [ ] 2.6 Change `spec.storageClassName` from `local-storage` to `nfs-storage`

## 3. Handle existing PV cleanup on re-run

- [ ] 3.1 Add a delete step in `tasks/persistent-volume.yml` that removes the old local-type PV (if it exists) before applying the new NFS-type PV, since Kubernetes does not allow changing a PV's volume source in-place

## 4. Update verification tests

- [ ] 4.1 Update `test_volume_is_create` in `molecule/default/tests/test_master.py` to check for `nfs-storage` instead of `local-storage`
- [ ] 4.2 Add assertion that the PV's `spec.nfs.server` and `spec.nfs.path` fields are present

## 5. Full integration verification cycle

- [ ] 5.1 Run destroy: `uv tool run --python 3.13 --with tox tox -e destroy -- --scenario-name=parallels`
- [ ] 5.2 Run converge-monorepo: `uv tool run --python 3.13 --with tox tox -e converge-monorepo -- --scenario-name=parallels` (SSH to fix any issues if needed)
- [ ] 5.3 Run verify-monorepo: `uv tool run --python 3.13 --with tox tox -e verify-monorepo -- --scenario-name=parallels`
