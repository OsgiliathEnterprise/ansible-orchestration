# PV NFS Kind

## Purpose

Expose NFS-backed storage to Kubernetes workloads through native NFS-type PersistentVolumes applied on the first master node, eliminating the dependency on worker-node mount paths for PV accessibility.

## Requirements

### Requirement: PV uses NFS volume source
The PersistentVolume manifest SHALL use an `nfs:` volume source instead of a `local:` volume source.

#### Scenario: PV template renders NFS fields
- **WHEN** the role generates the PV manifest
- **THEN** the manifest contains `spec.nfs.server` set to the NFS server hostname or IP
- **THEN** the manifest contains `spec.nfs.path` set to the full remote export path including subtree
- **THEN** the manifest does NOT contain `spec.local`

### Requirement: PV server address is derived from mountpoint configuration
The NFS server address SHALL be taken from the `host` field of the NFS mountpoint definition.

#### Scenario: Server address resolves correctly
- **WHEN** an NFS mountpoint defines `host: master.osgiliath.test`
- **THEN** `spec.nfs.server` is set to `master.osgiliath.test`

### Requirement: PV path combines remote export and subtree
The NFS path SHALL be the concatenation of the mountpoint's `remote` export path and the volume's `subtree`.

#### Scenario: Path resolves correctly
- **WHEN** an NFS mountpoint defines `remote: /var/nfs/volume` and a volume defines `subtree: /artefactrepo`
- **THEN** `spec.nfs.path` is set to `/var/nfs/volume/artefactrepo`

#### Scenario: Root subtree uses remote path only
- **WHEN** a volume has no subtree defined or subtree is empty
- **THEN** `spec.nfs.path` is set to the value of `remote` alone

### Requirement: PV creation runs on first master node
The PersistentVolume creation tasks SHALL execute on the first Kubernetes master node, not on worker nodes. The `nfs_mountpoints` variable and associated task execution MUST be triggered when the host is in the master group.

#### Scenario: Tasks run on master
- **WHEN** the role runs and the host is in `kube_masters_group`
- **THEN** the `nfs-mountpoints.yml` tasks execute
- **THEN** the PV manifest is rendered and applied via kubectl on that master

#### Scenario: Tasks do not run on worker nodes
- **WHEN** the role runs on a host in `kube_nodes_group` but NOT in `kube_masters_group`
- **THEN** the `nfs-mountpoints.yml` tasks do NOT execute

### Requirement: PV retains existing access and retention settings
The PersistentVolume SHALL maintain ReadWriteMany access mode and Retain reclaim policy.

#### Scenario: Access mode and reclaim policy are preserved
- **WHEN** the role generates the PV manifest
- **THEN** `spec.accessModes` contains `ReadWriteMany`
- **THEN** `spec.persistentVolumeReclaimPolicy` is set to `Retain`

### Requirement: Storage class reflects NFS backing
The PersistentVolume SHALL use a storage class name that indicates NFS-backed storage.

#### Scenario: Storage class is updated
- **WHEN** the role generates the PV manifest
- **THEN** `spec.storageClassName` is set to `nfs-storage` instead of `local-storage`

### Requirement: PV is verifiable as NFS type
A testinfra test SHALL verify that the PersistentVolume uses an NFS volume source.

#### Scenario: PV type verification passes
- **WHEN** the test runs on a host with kubectl access
- **THEN** `kubectl get pv -o json` shows `spec.nfs.server` and `spec.nfs.path` fields
- **THEN** the PV status is `Available`
- **THEN** the PV does not have node affinity restrictions
