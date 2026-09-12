# Design: Derive Kube Service Cluster IP

## Context

See proposal.md for motivation. The `Ipa-kubernetes-ca | add kube service cluster IP to IPA server hosts for Dogtag reachability check` task (`tasks/ipa-kubernetes-ca.yml`) is the single hard-coded consumer of the service cluster IP. Six other sites already derive it: `kube-install.yml` (certSANs), `ipa-kubernetes-ca.yml` (reverse-zone name, A record, PTR name/zone), and `ipa-api-server.yml` (cert SANs) — all using the idiom `(kube_service_cidr | default('10.96.0.0/12')) | ansible.utils.next_nth_usable(1)`. `kube_service_cidr` is defined in `defaults/main.yml` (`10.96.0.0/12`) and fed to `kubeadm` as `serviceSubnet`, so it is the cluster's source of truth.

## Goals / Non-Goals

**Goals:**

- Make the `/etc/hosts` entry derive from `kube_service_cidr`, consistent with the six existing consumers.
- Byte-identical behavior under the default CIDR.

**Non-Goals:**

- Refactoring the six existing derivation sites into a shared variable (repetitive but harmless; a separate cleanup if ever wanted).
- Any change to the entry's semantics (IP → `orchestration_host_hostname` mapping, target file, `delegate_to`, idempotent `state: present`).

## Decisions

### 1. Reuse the exact existing idiom

The `line:` value becomes:

```yaml
line: "{{ ((kube_service_cidr | default('10.96.0.0/12')) | ansible.utils.next_nth_usable(1)) }} {{ orchestration_host_hostname }}"
```

Chosen over introducing a new intermediate variable (e.g. `kube_service_ip` in `defaults/`): `defaults/` cannot reference other runtime variables portably for this purpose without adding a task or a `vars:` block, and the file already repeats the idiom six times — consistency with the local pattern beats a premature DRY refactor. The `default('10.96.0.0/12')` guard is kept even though `kube_service_cidr` is defined in `defaults/main.yml`, matching the surrounding tasks' defensive style.

Alternatives considered:

- *`ansible.utils.ipaddr` arithmetic on the network address* (`kube_service_cidr | ansible.utils.ipaddr('address') + 1`): rejected — `next_nth_usable(1)` is the established idiom here and correctly skips the network address for any prefix length.
- *New shared variable*: rejected — see above.

### 2. No other line changes

Only the `line:` value changes. Task name, `path`, `state`, `delegate_to`, `become`, and surrounding tasks stay as-is.

## Risks / Trade-offs

- [Default-CIDR regression] → impossible by construction: `next_nth_usable(1)` on `10.96.0.0/12` yields `10.96.0.1`, the exact value previously hard-coded.
- [Overridden CIDR leaves a stale default-IP line in `/etc/hosts` from a prior run] → pre-existing behavior of `lineinfile` (lines are never removed); the new line is additive and correct. Out of scope.
- [Repeated idiom] → accepted; six identical expressions in one file are greppable and consistent.

## Migration Plan

No migration. Converge under the default CIDR produces an identical `/etc/hosts` line; no state change on the IPA server. Rollback is a one-line `git revert`.

## Open Questions

None.
