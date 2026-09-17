# Design: Drain-Reset Generic Helm Sweep

## Context

See proposal.md for motivation. Current state of `tasks/drain-and-reset.yml` (run once on the first master via `delete.yml`, gated by `kube_masters_group`):

- Four `kubernetes.core.helm` tasks hard-code istio releases (`istio-ingress`, `istio-egress`, `istiod`, `istio-base` in `istio-system`), each with `failed_when: false`.
- The `helm` binary is **not installed** on the master — every one of those tasks fails with `Failed to find required executable "helm"` on every run, masked by `failed_when: false` (verified in converge logs).
- No helm releases exist in the current scenario: `tcharl.kubernetes` installs Calico via `kubectl apply` of tigera-operator manifests. The only helm source in the monorepo is the separate `tcharl.servicemesh` role (istio), which the scenario does not use.
- File convention: destroy-path tasks use `become: Yes`, `failed_when: false`, `kubeconfig: "{{ kube_config_path }}"`. The `kubernetes.core` collection (helm, k8s, k8s_drain, k8s_info) is already a dependency.

## Goals / Non-Goals

**Goals:**

- Uninstall every helm release present in the cluster (all namespaces, including non-`deployed`) before node drain, with zero hard-coded release names.
- Self-contained: the helm CLI is installed inline in the destroy path; no new persistent dependency on the converge path.
- No-op when the cluster has no releases; tolerant of API failures during the sweep (destroy-path convention).
- Preserve the existing ordering: sweep → drain → node-object deletion → `kubeadm reset`.

**Non-Goals:**

- Installing or persisting `helm` on the converge path.
- Graceful teardown: no waiting on finalizers (`wait: false`).
- Recovering releases whose release secrets were hand-deleted (orphaned objects die with `kubeadm reset` anyway).
- Changes to `tcharl.servicemesh` or any other role.

## Decisions

### 1. Inline helm CLI installation in `drain-and-reset.yml`

Chosen over adding an install task to `tcharl.kubernetes`: the destroy path is the only consumer, so the binary is fetched only when destroying, and no converge gains a dependency.

- `get_url` the static binary tarball from `https://get.helm.sh/helm-{{ helm_version }}-linux-{{ helm_arch }}.tar.gz` to `/tmp`, then `unarchive` (`remote_src`) with `include: ["linux-{{ helm_arch }}/helm"]` to `/tmp`, then `copy` the binary to `/usr/local/bin/helm` (`remote_src`, `mode: 0755`), all `become: true`. The modern helm tarball nests the binary under a `linux-<arch>/` top-level dir (verified: `linux-arm64/helm`), so a direct `unarchive` to `/usr/local/bin` would land the binary one level too deep; the extract-then-copy sequence places it exactly at `/usr/local/bin/helm`.
- `helm_version` pinned in `defaults/main.yml` (one-line bump to upgrade).
- `helm_arch` derived from `uname -m` output (`x86_64` → `amd64`, `aarch64` → `arm64`) as a task-local var — covers Parallels and KVM guests on both host architectures. Detected with a `command: uname -m` task (registered, `changed_when: false`) **rather than** the `ansible_arch` fact: the destroy path runs before `facts.yml` gathers facts, and the tox fact cache does not reliably populate `ansible_arch` at this point (verified: both the play-level `Gathering Facts` and an explicit `setup` with `filter: ansible_arch` return no `ansible_arch`, so the template errors with `ansible_arch is undefined`). `uname -m` bypasses fact caching entirely.
- Skipped when `/usr/local/bin/helm` already exists (`stat`-based `when:`) → idempotent, and a pre-seeded binary (offline hosts) is honored without download.
- **Fails loudly**: no `failed_when: false` on the install task — a missing CLI must not silently disable the sweep (the exact disease this change removes).

Alternatives considered:

- *Install in `tcharl.kubernetes`*: rejected — persists a binary nobody else uses; every converge pays for it.
- *Pure k8s-API discovery (secrets labeled `owner=helm`)*: rejected — discovery alone doesn't give a clean uninstall; `helm uninstall` is still required, which needs the CLI anyway.

### 2. Discovery via `helm list -A --all -o json`

```yaml
- name: Drain-and-reset | list all helm releases
  ansible.builtin.command: >-
    helm list -A --all -o json --kubeconfig {{ kube_config_path }}
  become: Yes
  changed_when: false
  failed_when: false
  register: _helm_releases
```

- `--all` includes `failed` and `uninstalled` records (a half-installed chart must not survive the destroy).
- `--kubeconfig` mirrors how the existing tasks pin the admin kubeconfig, so discovery and uninstall share the same cluster context.
- `failed_when: false` + empty default downstream: an unreachable API during the sweep is non-fatal (spec: sweep failure is not fatal).
- Alternatives: `helm list -q` (names only — loses namespaces) and shell loops (rejected: repo culture is native modules over shell).

### 3. Uninstall via `kubernetes.core.helm` loop

```yaml
- name: Drain-and-reset | uninstall all helm releases
  kubernetes.core.helm:
    name: "{{ item.name }}"
    namespace: "{{ item.namespace }}"
    release_state: absent
    wait: false
    kubeconfig: "{{ kube_config_path }}"
  become: Yes
  failed_when: false
  loop: "{{ (_helm_releases.stdout | default('[]') | from_json) | selectattr('status', 'in', ['deployed', 'failed']) | list }}"
```

- Module over shell (repo convention: "replace shell commands by ansible native").
- `wait: false` — the destroy path never blocks on finalizers; `kubeadm reset` follows on the same node.
- The loop filters `--all`'s `uninstalled` entries (helm cannot re-uninstall them) and stays a no-op on an empty/failed list.
- Per-release `failed_when: false`: one bad release must not abort the sweep of the rest.

### 4. Removal of the four istio tasks

Deleted outright — the sweep covers the `tcharl.servicemesh` case automatically (its releases and PDBs disappear together). No istio knowledge remains in the file.

### 5. Placement and ordering

The three new tasks (install → list → uninstall loop) replace the four istio tasks at the top of `drain-and-reset.yml`, before `k8s_drain`. The drain, node-deletion, and `kubeadm reset` tasks are untouched.

## Risks / Trade-offs

- [get.helm.sh unreachable at destroy time (offline host) → install fails → destroy path aborts] → mitigated by the `stat`-based skip: pre-seeding `/usr/local/bin/helm` (e.g. in prepare) bypasses the download. Per the spec, a genuinely broken download is fatal by design — silent no-op is the disease we are removing.
- [Pinned helm version drifts from release tooling] → single `helm_version` variable; bump is one line.
- [Arch detection via `uname -m` returns an unexpected value on an exotic guest] → the `replace()` chain maps only the two known values (`x86_64`, `aarch64`); any other value yields an unresolvable tarball URL and the install fails loudly (no silent no-op). Acceptable: the scenario targets amd64/arm64 guests only.
- [Release created between list and loop] → destroy path; `kubeadm reset` is the final backstop.
- [Uninstalling a release whose resources are owned by static-pod-like objects] → `wait: false`; residual objects are wiped with the node.
- [Behavior change vs. old tasks] → none observable: the old tasks always failed (no CLI) or no-op'd (no releases).

## Migration Plan

No data or state migration. Deploy by running the destroy+converge cycle on the parallels scenario: the sweep must no-op cleanly on a release-free cluster (list task registers `[]`). To exercise the sweep itself, optionally `helm install` a test chart on the master before a destroy run and confirm it is removed before the drain. Rollback is a plain `git revert` — the removed tasks were inert, so nothing working regresses.

## Open Questions

None — helm version pin value is chosen at implementation time (current stable v3).
