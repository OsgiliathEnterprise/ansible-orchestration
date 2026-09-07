## Context

See proposal.md for motivation. Verified facts shaping this change:

- `kube-install-refresh-join.yml` is referenced by no include/import anywhere in the role or molecule playbooks (grep across `tasks/`, `molecule/`).
- Its input `kubernetes_join_command` arrives as `""` from `kube-install.yml:101`; on master, `tcharl.kubernetes/tasks/main.yml:66-69` may override it with a fact from `kubeadm init` output — but nothing in this role consumes that fact after the file's removal.
- `tcharl.kubernetes/tasks/node-setup.yml:4,12-13` runs the built-in join only when `kubernetes_join_command | trim | length > 0`, so the empty value is a functional disable, not dead code.

## Goals / Non-Goals

**Goals:**
- Remove the orphaned file and any reader confusion it causes.
- Make the intent of `kubernetes_join_command: ""` explicit in `kube-install.yml`.

**Non-Goals:**
- No changes to `tcharl.kubernetes` (its fact-setting is owned by that role).
- No spec deltas — no requirement references this file.

## Decisions

**D1: Delete rather than nativize the two shell tasks.**
The file's output (`kubernetes_join_command` reconstruction) has zero consumers; converting its openssl calls to native modules would be work on code that should not exist. The no-dead-code rule (codified in change `agents-md-practices-c4`) makes deletion the only sensible option.
*Alternative considered:* keep and nativize — rejected, it preserves a misleading artifact of a superseded join design.

**D2: Keep `kubernetes_join_command: ""` with an explanatory comment.**
Verified functional (disables `tcharl.kubernetes` built-in node join). The existing comment block at L74-78 explains the *history* (hash computation removed, join moved to `kube-install-join-node.yml`) but not the *purpose of the empty value*; extend it with one line stating the variable is intentionally empty.
*Alternative considered:* delete the variable too — rejected; that would re-enable the built-in join on nodes and break the flow.

## Risks / Trade-offs

- [Something outside the role includes the file] → Mitigation: grep across `tasks/`, `molecule/`, and the whole role directory before deletion; Ansible task files are only reachable via include/import, both of which were checked.
- [Converge behavior unexpectedly changes] → Mitigation: run full converge + idempotence cycle after deletion; expected result is byte-identical task output since the file was never in an execution path.

## Migration Plan

Delete file, update comment, run converge + idempotence verification (per role AGENTS.md tox commands). Rollback = git restore of the two files. No data migration.

## Open Questions

None — the functional-vs-dead status of `kubernetes_join_command` was resolved by reading `tcharl.kubernetes/tasks/node-setup.yml`.
