# tcharl.ansible_orchestration - Agent Instructions

## Inheritance

See [`../AGENTS.md`](../AGENTS.md) for shared monorepo rules and conventions.

## Role Purpose

This role orchestrates a full infrastructure stack: FreeIPA server, Kubernetes master/nodes, NFS, containerd, and related services. It is the integration role that exercises many other roles in the monorepo.

## Dependencies

- **requirements-standalone.yml** - Full dependency list including local roles (`tcharl.freeipa_server`, `tcharl.ansible_securehost`, `tcharl.kubernetes`, etc.)
- **requirements-monorepo.yml** - Minimal external roles only (geerlingguy.swap, geerlingguy.containerd, etc.). Local roles are resolved from the monorepo.

## VM Topology (parallels scenario)

| Host | Groups | Purpose |
|------|--------|---------|
| `idm.osgiliath.test` | ipaservers | FreeIPA server (5120MB RAM) |
| `master.osgiliath.test` | ipaclients, kube_master | K8s master + IPA client (5120MB RAM, 840GB disk) |
| `node1.osgiliath.test` | ipaclients, kube_node | K8s worker + IPA client (5120MB RAM) |

## Task Flow (L3)

`tasks/main.yml` include graph (every file below exists under `tasks/`):

```
main.yml
|-- delete.yml                    [reset_kube]
|   |-- drain-and-reset.yml
|   |-- delete-ipa-cleanup.yml
|   |-- delete-configuration.yml
|       |-- destroy-kubelet-volumes.yml
|       |-- role: robertdebock.reboot
|-- requirements.yml
|   |-- role: geerlingguy.swap
|   |-- snippet_containerd.yml
|       |-- role: geerlingguy.containerd
|-- fix-requirements.yml          [kube_masters_group or kube_nodes_group]
|-- prereq.yml
|-- facts.yml
|-- cri.yml
|-- firewall.yml                  [role: tcharl.ansible_routing x3]
|-- kube-install.yml              [master: kubeadm init | node: packages only]
|   |-- role: tcharl.kubernetes   (join disabled: kubernetes_join_command: "")
|-- ipa-certs.yml                 [kube_masters_group]
|   |-- ipa-kubernetes-ca.yml
|   |-- ipa-master.yml
|   |-- ipa-api-server.yml
|   |-- ipa-front-proxy.yml
|   |-- kube-apiserver-kubelet-client.yml
|-- kube-install-join-node.yml    [kube_nodes_group]
|-- ipa-pki-swap.yml              [kube_masters_group]
|-- kube-firewall.yml             [kube_masters_group or kube_nodes_group]
|-- admin-user.yml                [kube_masters_group]
|-- nfs-mountpoints.yml           [kube_masters_group + nfs_mountpoints]
    |-- _server-inner.yml
        |-- persistent-volume.yml (k8s PV; delegate_to master)
```

Node join is intentionally deferred: `kube-install.yml` on nodes only installs packages (join disabled via `kubernetes_join_command: ""`), and `kube-install-join-node.yml` runs only after the master's `ipa-certs.yml` / `ipa-pki-swap.yml` post-processing completes, so the ConfigMap CA is stable before join-time hash computation.

Unreferenced task files (not in the graph): `ipa-admin-cert.yml`, `ipa-node-sync.yml`, `nfs-server-group.yml`, `nfs-mountpoint.yml` — orphans per the no-dead-code rule; delete or re-wire.

## Execution

```bash
# Full cycle
uv tool run --python 3.13 --with tox tox -e destroy -- --scenario-name=parallels
uv tool run --python 3.13 --with tox tox -e converge-monorepo -- --scenario-name=parallels
# Can login to machines and inspect state here
uv tool run --python 3.13 --with tox tox -e verify-monorepo -- --scenario-name=parallels
```

## Known Issues

- IPA server can fail to start if LDAP data is stale from previous runs. The prepare phase includes cleanup steps to handle this.
- Converge can take 5-15 minutes depending on IPA installation speed.

## Key Files

- `molecule/parallels/prepare.yml` - Pre-converge host preparation (IPA setup, NFS, etc.)
- `molecule/parallels/converge.yml` - Main convergence playbook
- `molecule/parallels/tests/test_converge.py` - Testinfra verification tests
