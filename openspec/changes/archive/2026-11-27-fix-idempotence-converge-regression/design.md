# Design

## Context

Commit `95c9688` (steady-state idempotence) ended the two-writer oscillation on `/etc/containerd/config.toml`: `snippet_containerd.yml` imports `geerlingguy.containerd` with `containerd_config_default_write: False`, and `tasks/fix-requirements.yml` became the single writer (render `containerd config default` → regex-derive → content-idempotent `copy`). The previous layout had the template + `meta: flush_handlers` in the same file; the move dropped the flush. `grep -rn flush_handlers tasks/` confirms the role has none.

Reproduced failure (parallels, fresh VMs, converge exit 2):

- `01:12:56.064` — containerd (PID 17782) starts; this is the role's refresh handler fired **once** by the `import_role` role-end flush, before the config write. It loads a stale v1-format file ("Configuration migrated from version 0").
- `01:12:56.857` — `Fix Requirements | Deploy containerd configuration` writes the derived v4 config (`changed=true`, mtime on disk), notifying the handler — but nothing flushes it; the log contains exactly one `Handler | refresh containerd` line, and it precedes the deploy task.
- `01:14:23` — `kubeadm init` fails: `[ERROR CRI]: ... unknown service runtime.v1.RuntimeService`. The still-running PID 17782 daemon never read the deployed file.
- Downstream: `kubernetesNodes` profile is never created in FreeIPA; both workers exhaust the 180-attempt profile gate in `tasks/kube-install-join-node.yml` and fail the structured join diagnosis. The join gate and diagnosis behaved exactly as specified.

## Goals / Non-Goals

- Goals: fresh-install converge green (converge → verify); steady-state all-changed=0 preserved; minimal diff.
- Non-Goals: re-touching the single-writer design, the handler itself, geerlingguy overrides, or the join gates (all correct as-is).

## Decisions

1. **`meta: flush_handlers` at the end of `tasks/fix-requirements.yml`** (after the deploy task). The include runs exactly where the notification is queued (same play, kube master/worker hosts), so the flush fires the pending restart immediately and is a no-op when nothing is pending (steady state). Rejected alternatives:
   - Reverting the single-writer refactor into the snippet — reintroduces the oscillation the idempotence change removed.
   - Unconditional `systemd: state: restarted` task — breaks the all-changed=0 steady-state proof and restarts containerd needlessly.
   - A second flush task guarded by the deploy registration — `meta` cannot be conditional; the unconditional flush is already conditional in effect (it only runs pending handlers).
2. **Document the flush as load-bearing** in the `fix-requirements.yml` header comment, so the invariant (writer and restart are one unit) cannot silently regress again.

## Risks / Trade-offs

- A flush surfaces handler failures at the deploy point instead of end of play — desirable: a failed containerd restart should abort before kubeadm touches the runtime.
- `flush_handlers` flushes any pending handler, but at that point in the play the containerd refresh handler is the only one that can be pending: the snippet's own notification is already flushed at `import_role` end (visible in the reproduction log), and the NetworkManager notification source (`firewall.yml`) runs later in `main.yml`.

## Migration Plan

Rollback = revert the one-task commit; no state implications (handler semantics unchanged).

## Open Questions

None. Other suspects from the idempotence window were cleared against the reproduction log: no `Cannot contact any KDC` occurrences (the dropped prepare firewalld task is not implicated), and the idm-side `FAILED!` lines are check-then-act probes (`lvs`, `xfs_info`) with `changed_when_result: false`.
