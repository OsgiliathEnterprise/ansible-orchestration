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
