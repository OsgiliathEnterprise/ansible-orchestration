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
| `idm.osgiliath.test` | ipaservers | FreeIPA server (5120MB RAM, +7.6GB secondary disk) |
| `master.osgiliath.test` | ipaclients, kube_master | K8s master + IPA client (8192MB RAM) |
| `node1.osgiliath.test` | ipaclients, kube_node | K8s worker + IPA client (8192MB RAM) |
| `node2.osgiliath.test` | ipaclients, kube_node | K8s worker + IPA client (8192MB RAM) |

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
|   |-- ipa-kubernetes-ca.yml     (CA #1: serving cert / trust anchor)
|   |-- ipa-kubeclusteradm-ca.yml (CA #2: client certs)
|   |-- ipa-master.yml
|   |-- ipa-api-server.yml
|   |-- ipa-front-proxy.yml
|   |-- kube-apiserver-kubelet-client.yml
|   |-- ipa-controlplane-clients.yml
|-- kube-install-join-node.yml    [kube_nodes_group]
|   |-- kube-node-cert.yml        (per-node client cert from the kubeclusteradm CA #2)
|-- ipa-kube-admin-credential.yml [kube_masters_group; kinit]
|-- admin-user.yml                [kube_masters_group; CA #2 cert + admin.conf re-embed + kubectl get nodes verification]
|-- ipa-pki-swap.yml              [kube_masters_group]
|   |-- calico-ca-recovery.yml    (no-op when Calico is not installed)
|-- kube-firewall.yml             [kube_masters_group or kube_nodes_group]
|-- ipa-cert-renewal.yml          [kube_masters_group or kube_nodes_group]
|-- nfs-mountpoints.yml           [kube_masters_group + nfs_mountpoints]
    |-- _server-inner.yml
        |-- persistent-volume.yml (k8s PV; delegate_to master)
```

Node join is intentionally deferred: `kube-install.yml` on nodes only installs packages (join disabled via `kubernetes_join_command: ""`). `kube-install-join-node.yml` runs after master's `ipa-certs.yml` — which has already swapped the API server to an IPA-signed serving certificate — but before `ipa-pki-swap.yml`. The node fetches its trust anchor directly from FreeIPA (delegated to idm), gates on the kubernetesNodes profile existing, and only joins once the API validates against that anchor; it no longer depends on master post-processing state.

Admin credential ordering: `ipa-pki-swap.yml`'s verification gates (KCM lease, scheduler Ready, kubectl) authenticate with `admin.conf`, whose client certificate must be the CA #2-issued one to be trusted by the 2-CA bundle (the kubeadm CA was dropped from it). `admin-user.yml` therefore runs before `ipa-pki-swap.yml`, and the end-to-end `kubectl get nodes` verification runs at the end of `admin-user.yml` (after `admin.conf` is re-embedded), not in `ipa-kube-admin-credential.yml`.

## Execution

```bash
# Full cycle
uv tool run --python 3.13 --with tox tox -e destroy -- --scenario-name=parallels
uv tool run --python 3.13 --with tox tox -e converge-monorepo -- --scenario-name=parallels
# Can login to machines and inspect state here
uv tool run --python 3.13 --with tox tox -e verify-monorepo -- --scenario-name=parallels
```

**Note for Agents**: Do not take command timeouts into consideration; wait until the end of long-running tasks.

## Known Issues

- IPA server can fail to start if LDAP data is stale from previous runs. The prepare phase includes cleanup steps to handle this.
- Converge can take 5-15 minutes depending on IPA installation speed.

## Key Files

- `molecule/parallels/prepare.yml` - Pre-converge host preparation (IPA setup, NFS, etc.)
- `molecule/parallels/converge.yml` - Main convergence playbook
- `molecule/parallels/tests/test_converge.py` - Testinfra verification tests
