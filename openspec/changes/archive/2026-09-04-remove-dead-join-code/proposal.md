## Why

`tasks/kube-install-refresh-join.yml` is orphaned: no playbook or task file includes it, and its purpose (reconstructing a `kubeadm join` command with a CA hash refreshed from the cluster-info ConfigMap) was superseded by the direct-copy join in `kube-install-join-node.yml`. It carries two shell tasks that were flagged in review, but the correct fix is deletion rather than nativizing them. Leaving it in place misleads readers into thinking token+CA-hash discovery is still part of the flow.

## What Changes

- **Delete** `tasks/kube-install-refresh-join.yml` (79 lines: ConfigMap fetch via `uri`, two openssl CA-hash shell tasks, join-command reconstruction).
- **Keep** `kubernetes_join_command: ""` in `tasks/kube-install.yml:101`. It is *not* dead — it intentionally disables the built-in node join in `tcharl.kubernetes` (`node-setup.yml` only joins when the variable is non-empty), because nodes are joined out-of-band by `kube-install-join-node.yml`.
- **Clarify** the existing comment block at `tasks/kube-install.yml:74-78` to state explicitly that `kubernetes_join_command` is set empty on purpose (built-in join disabled; join handled by `kube-install-join-node.yml`).

## Capabilities

### New Capabilities

(None — pure refactor / dead-code removal.)

### Modified Capabilities

(None — no requirement references the deleted file; behavior is unchanged because the file was never included.)

## Impact

- `tasks/kube-install-refresh-join.yml` — removed.
- `tasks/kube-install.yml` — comment clarification only (no variable or task change).
- No converge/idempotence behavior change: the deleted file was not in any execution path. The `kubernetes_join_command` fact set inside `tcharl.kubernetes` on master becomes unused within this role but is left untouched (owned by that role).
