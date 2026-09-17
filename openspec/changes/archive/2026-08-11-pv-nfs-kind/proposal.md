## Why

The current PersistentVolume uses a `local:` volume source pointing to a locally-mounted NFS path, which ties the PV to a specific node and requires manual mount management on each worker. Using an NFS-type PV (`spec.nfs`) allows Kubernetes to handle the mount directly, making the PV accessible from any node with network access to the NFS server.

## What Changes

- Replace `local:` volume source in the PersistentVolume template with `nfs:` volume source
- The PV will reference the NFS server host and remote export path directly instead of a local filesystem path
- Update storage class name from `local-storage` to an appropriate NFS-oriented class
- Remove node-specific mount dependency for PV accessibility (the NFS client mount on the worker is no longer required for PV access, though it may remain for other purposes)
- Update verification tests that check PV properties

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pv-nfs-kind`: New spec describing the NFS-type PersistentVolume capability replacing the local-volume approach. Covers PV template structure, NFS server/path configuration, and verification.

## Impact

- **templates/persistent-volume.yml.j2** — volume source changed from `local:` to `nfs:`
- **tasks/persistent-volume.yml** — may need variable adjustments for NFS fields
- **molecule/default/tests/test_master.py** — PV verification test needs update
- **NFS client mount on worker nodes** — the local mount path is no longer required for Kubernetes PV access, simplifying node preparation
