## Why

The monorepo `AGENTS.md` files carry execution commands and role structure but encode none of the *coding practices* that recent changes have converged on (prefer native Ansible modules over shell, idempotency conventions, no-dead-code). Agents working in this repo repeatedly re-introduce shell tasks where a native module exists — the current review found ~15 such cases across four task files. There is also no structured C4 view of the platform topology, so cross-host reasoning (which VM runs what, which CA signs what) has to be reconstructed from scattered task files each time.

## What Changes

- Add a **Practices** section to `ansible/roles/AGENTS.md` (the shared monorepo instructions):
  - A native-module preference table mapping common shell patterns (`touch`, `sed -i`, `cat > file`, polling loops, openssl cert inspection) to their native Ansible / collection equivalents.
  - An explicit **shell-exception rule**: when no native equivalent exists (e.g. `openssl verify` chain validation, PEM→DER hashing, `kubeadm reset`, `pkill`), the task must carry a comment stating why no native module applies.
  - Idempotency conventions: do not paper over non-idempotent shell with `changed_when`; prefer modules that are idempotent for free.
  - A **no-dead-code rule**: every included task file must be referenced; every registered variable must be consumed.
- Add a structured **C4 architecture** section to the role's `AGENTS.md` (`tcharl.ansible_orchestration/AGENTS.md`) with three levels:
  - **L1 Context**: Ansible control node orchestrating the three VMs (idm / master / node1).
  - **L2 Container**: per-host services and ports (FreeIPA HTTP/LDAP/KDC/PKI, K8s static pods + kubelet + containerd, NFS server on idm).
  - **L3 Component**: the role's task-flow graph (`main.yml` → include files) plus a PKI trust diagram showing the dual-CA transition state (IPA `kubernetes-ca` vs kubeadm self-signed CA, bridged by `ca-bundle.crt`).

## Capabilities

### New Capabilities

(None — pure documentation; no spec-level behavior changes.)

### Modified Capabilities

(None — no requirement changes. This change only adds agent-facing guidance and diagrams to existing `AGENTS.md` files.)

## Impact

- `ansible/roles/AGENTS.md` (shared monorepo instructions) — new **Practices** section.
- `tcharl.ansible_orchestration/AGENTS.md` (role instructions) — new **C4 Architecture** section.
- No task, default, or playbook code changes; no effect on converge/idempotence behavior.
