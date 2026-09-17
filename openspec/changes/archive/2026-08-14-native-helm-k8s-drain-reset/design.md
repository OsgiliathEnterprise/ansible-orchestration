## Context

`drain-and-reset.yml` uses 7 `ansible.builtin.command` tasks for Helm chart removal, node draining, node deletion, and kubeadm reset. The project has `kubernetes.core` (6.5.0) installed with native modules for all operations except kubeadm reset.

## Goals / Non-Goals

**Goals:**
- Replace 4x `helm delete` with `kubernetes.core.helm` (state=absent)
- Replace `kubectl drain` with `kubernetes.core.k8s_drain`
- Replace `kubectl delete node --all` with `kubernetes.core.k8s` (state=absent, kind=Node)

**Non-Goals:**
- Replacing `kubeadm reset -f` — no native module exists

## Decisions

**Use `kubernetes.core.helm` for chart removal:** The module accepts `name`, `namespace`, and `state: absent` to delete releases. It handles idempotency (no-op if already deleted) and proper changed_when detection natively, replacing the fragile string-matching on stdout.

**Use `kubernetes.core.k8s_drain` for node drain:** Parameters map directly: `force: true`, `ignore_daemonsets: true`, `delete_emptydir_data: true`, `grace_period_seconds: 800`. This replaces shell string interpolation with structured parameters.

**Use `kubernetes.core.k8s` for deleting all nodes:** With `kind: Node`, `state: absent`, and `resource_filter: []` (empty filter to match all), the module deletes every node resource. Alternatively, list nodes first with `k8s_info` then iterate — but the direct approach is simpler if supported.

**Kubeconfig handling:** The current tasks use `become: Yes` without explicit kubeconfig path, relying on default `/root/.kube/config` or `KUBECONFIG`. The native modules accept a `kubeconfig` parameter — we should pass it explicitly for reliability. Need to determine the correct kubeconfig path used in this role (likely `/etc/kubernetes/admin.conf`).

## Risks / Trade-offs

[Risk] `kubernetes.core.k8s` with `state: absent` and no name may not delete all nodes as expected → Mitigation: verify module behavior; if needed, list first with `k8s_info` then iterate
[Risk] The kubeconfig path needs to be correct for the modules to authenticate → Use same default location that existing commands rely on
