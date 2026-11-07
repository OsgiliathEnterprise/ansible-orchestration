# tcharl.ansible_orchestration - Agent Instructions

## Inheritance

See [`../AGENTS.md`](../AGENTS.md) for shared monorepo rules and conventions.

## Role Purpose

This role orchestrates a full infrastructure stack: FreeIPA server, Kubernetes master/nodes, NFS, containerd, and related services. It is the integration role that exercises many other roles in the monorepo.

## Dependencies

- **requirements-standalone.yml** - Full dependency list including local roles (`tcharl.freeipa_server`, `tcharl.ansible_securehost`, `tcharl.kubernetes`, etc.)
- **requirements-monorepo.yml** - Minimal external roles only (geerlingguy.swap, geerlingguy.containerd, etc.). Local roles are resolved from the monorepo.

## VM Topology

| Scenario | Host | Groups | Purpose |
|----------|------|--------|---------|
| parallels | `idm.osgiliath.test` | ipaservers | FreeIPA server (5120MB RAM, +7.6GB secondary disk) |
| parallels | `master.osgiliath.test` | ipaclients, kube_master | K8s master + IPA client (8192MB RAM) |
| parallels | `node1.osgiliath.test` | ipaclients, kube_node | K8s worker + IPA client (8192MB RAM) |
| parallels | `node2.osgiliath.test` | ipaclients, kube_node | K8s worker + IPA client (8192MB RAM) |
| default | `idm.osgiliath.test` | ipaservers | FreeIPA server (2048MB RAM) |
| default | `master.osgiliath.test` | ipaclients, kube_master | K8s master + IPA client (2048MB RAM) |
| default | `node1.osgiliath.test` | ipaclients, kube_node | K8s worker + IPA client (2048MB RAM) |
| default | `node2.osgiliath.test` | ipaclients, kube_node | K8s worker + IPA client (2048MB RAM) |
| kvm | `idm.osgiliath.test` | ipaservers | FreeIPA server (2048MB RAM, +5G secondary disk) |
| kvm | `master.osgiliath.test` | ipaclients, kube_master | K8s master + IPA client (2048MB RAM) |
| kvm | `node1.osgiliath.test` | ipaclients, kube_node | K8s worker + IPA client (2048MB RAM) |

The `kvm` scenario is the single-worker CI topology: it has no `node2`, and its test suite (`molecule/kvm/tests/`) links only the single-worker-safe tests — `test_two_node.py` (two-worker guard) is deliberately not linked (see Key Files).

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
|   |-- ipa-ca-acl-prejoin.yml    (pre-join CA ACL grants; -> ipa-ca-acl-host.yml)
|   |-- ipa-master.yml
|   |-- ipa-api-server.yml
|   |-- ipa-front-proxy.yml
|   |-- kube-apiserver-kubelet-client.yml
|   |-- ipa-controller-manager-client.yml
|   |-- ipa-scheduler-client.yml
|-- kube-install-join-node.yml    [kube_nodes_group]
|   |-- kube-node-cert.yml        (node-local: own host-keytab ticket + key/CSR + ipacert on CA #2)
|-- ipa-kube-admin-credential.yml [kube_masters_group; keytab-first + password fallback]
|-- admin-user.yml                [kube_masters_group; CA #2 cert + admin.conf re-embed + kubectl get nodes verification]
|-- ipa-pki-swap.yml              [kube_masters_group]
|   |-- calico-ca-recovery.yml    (no-op when Calico is not installed)
|-- kube-firewall.yml             [kube_masters_group or kube_nodes_group]
|-- ipa-cert-renewal.yml          [kube_masters_group or kube_nodes_group]
|   |-- ipa-ca-acl-host.yml       (steady-state CA ACL re-assert for renewal identities)
|-- nfs-mountpoints.yml           [kube_masters_group + nfs_mountpoints]
    |-- _server-inner.yml
        |-- persistent-volume.yml (k8s PV; delegate_to master)
```

Node join is intentionally deferred: `kube-install.yml` on nodes only installs packages (join disabled via `kubernetes_join_command: ""`). `kube-install-join-node.yml` runs after master's `ipa-certs.yml` — which has already swapped the API server to an IPA-signed serving certificate — but before `ipa-pki-swap.yml`. The node fetches its trust anchor directly from FreeIPA (delegated to idm), gates on the kubernetesNodes profile existing, and only joins once the API validates against that anchor; it no longer depends on master post-processing state.

Admin credential ordering: `ipa-pki-swap.yml`'s verification gates (KCM lease, scheduler Ready, kubectl) authenticate with `admin.conf`, whose client certificate must be the CA #2-issued one to be trusted by the 2-CA bundle (the kubeadm CA was dropped from it). `admin-user.yml` therefore runs before `ipa-pki-swap.yml`, and the end-to-end `kubectl get nodes` verification runs at the end of `admin-user.yml` (after `admin.conf` is re-embedded), not in `ipa-kube-admin-credential.yml`.

## Kerberos Ticketing

This role never uses shell `kinit` or the ambient per-user ticket cache (`~/.k5.<user>`):

- **Scratch caches** — ticket acquisition is a `community.general.krb_ticket` task into a
  per-purpose scratch cache `{{ kube_scratch_cache_dir }}/<principal>.<purpose>.ccache`
  (`/run/krb5cc`, root-only `0700`; pre-cleared first, so a stale/expired ticket can never
  be reused). Downstream `ipa`/`ipacert` consumers — including idm-delegated ones — inherit
  the cache via `env: KRB5CCNAME`. `krb_ticket` shells to `kinit -c` and cannot create the
  cache's parent directory: `requirements.yml` creates the directory on every targeted host
  **and on idm by delegation** (idm is never a play target), and `delete-ipa-cleanup.yml` —
  which runs before requirements on the `reset_kube` path — carries the same delegated task
  at its top.
- **Keytab usability probes** — keytab-first flows probe with a block/rescue `krb_ticket`
  into a scratch cache (`kca_keytab_usable`); a rotated keytab fails the probe and the flow
  falls back to the admin password.
- **Native keytab export** — the `kubeclusteradm` keytab is exported on idm with
  `kadmin.local -q "ktadd -norandkey -k {{ kube_idm_keytab_path }} ..."` (non-rotating,
  writes directly to the unit state directory). The file must be deleted before a
  re-export because `ktadd` appends, and it is created 0644 — a follow-up `file` task
  locks it down to root-only 0600. The master's copy under `{{ kube_credential_folder }}`
  is shuttled with `slurp` + `copy: content:` (no base64-in-stdout).
- **Cert enrollment is host-local** — each node mints its own ticket from its own
  `/etc/krb5.keytab` (`host/<hostname>`) and runs its own `ipacert` enrollment locally
  (`kube-node-cert.yml` on workers, the cert files plus `kube-cert-renew.sh` on the
  master). The admin password never authenticates to the IPA API from a kube host:
  admin-identity module calls are delegated to idm.
- **Systemd timer tickets** — `kube-cert-renew.service` sets `StateDirectory=kube-cert-renew`
  and `Environment=KRB5CCNAME=FILE:/var/lib/kube-cert-renew/ccache`; the script pre-clears
  that cache so a stale ticket is never reused.
- Ticket tasks report no change (the scratch cache is ephemeral state, not configuration).

## Execution

```bash
# Full cycle (parallels, two workers)
uv tool run --python 3.13 --with tox tox -e destroy -- --scenario-name=parallels
uv tool run --python 3.13 --with tox tox -e converge-monorepo -- --scenario-name=parallels
# Can login to machines and inspect state here
uv tool run --python 3.13 --with tox tox -e verify-monorepo -- --scenario-name=parallels

# Single-worker cycle (kvm, Linux; the CI topology — also runnable via
# `tox -e test-exec-monorepo -- --scenario-name=kvm`)
uv tool run --python 3.13 --with tox tox -e destroy -- --scenario-name=kvm
uv tool run --python 3.13 --with tox tox -e converge-monorepo -- --scenario-name=kvm
uv tool run --python 3.13 --with tox tox -e verify-monorepo -- --scenario-name=kvm
```

The `verify` step is mandatory after a successful converge — it is the gate that proves the
recovery (all nodes Ready, per-pod evidence, PV mounts) actually took effect, not merely
that converge exited 0.

The `kvm` scenario overrides `kubernetes_rollout_wait_timeout` in `molecule/kvm/converge.yml` (600 vs role default 300) for the constrained single-worker CI topology; the value is calibrated from the measured calico wait duration.

**Note for Agents**: Do not take command timeouts into consideration; wait until the end of long-running tasks.

## Known Issues

- IPA server can fail to start if LDAP data is stale from previous runs. The prepare phase includes cleanup steps to handle this.
- A converge killed during the FreeIPA install leaves `/var/lib/pki/pki-tomcat`, `/var/lib/ipa`, and DS residues that make every later install die in pkispawn (`--uninstall` at stage CREATED does not remove them). Recover by uninstalling, wiping those residues, then verifying package integrity with `rpm -V` on all `dogtag-pki*` packages and restoring any `missing` RPM paths — do **not** remove RPM-owned systemd state (`pki-tomcatd.target.wants`) or `/var/log/pki`, pkispawn assumes both exist. Or simply destroy the VMs instead.
- Converge can take 5-15 minutes depending on IPA installation speed.

## Key Files

- `molecule/parallels/prepare.yml` - Pre-converge host preparation (IPA setup, NFS, etc.)
- `molecule/parallels/converge.yml` - Main convergence playbook
- `molecule/default/tests/` - Shared testinfra suite, source of truth: `conftest.py`, `test_master.py`, `test_node.py`, `test_two_node.py` (two-worker guard).
- `molecule/kvm/tests/` - Per-file symlinks to `../../default/tests/` (`conftest.py`, `test_master.py`, `test_node.py`); `test_two_node.py` is deliberately not linked (single-worker topology). Convention: a new shared test file must also be mirrored as a per-file symlink into `kvm/tests/` in the same change — the link set is the scenario's explicit test selection.
- `molecule/parallels/tests` - Directory symlink → `../default/tests` (full suite, includes `test_two_node.py`).
- `molecule/parallels-sequential/` - Scenario override verifying the serial recovery path (`calico_recovery_max_unavailable: 1` in `converge.yml`); reuses `parallels` prepare (shared VM topology).
