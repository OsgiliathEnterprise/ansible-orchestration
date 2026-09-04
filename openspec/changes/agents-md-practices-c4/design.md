## Context

See proposal.md for motivation. Current state: `ansible/roles/AGENTS.md` (shared monorepo instructions) contains Context, Execution Commands, Scenario Selection, Rules, and Role Structure — but no coding practices and no architecture diagrams. The role's own `AGENTS.md` has a VM topology table and key-file list but no task-flow or PKI-trust picture. All facts needed for the diagrams (hosts, ports, paths, CA relationships) are verifiable in `tasks/`, `molecule/parallels/converge.yml`, and `defaults/`.

## Goals / Non-Goals

**Goals:**
- Codify the native-module-over-shell practice with a concrete pattern→module table so agents don't re-litigate it per task.
- Provide L1/L2 C4 diagrams of the platform topology in the shared master AGENTS.md (every role agent needs this context).
- Provide an L3 task-flow graph and the dual-CA PKI trust diagram for the orchestration role, since that is where cross-host reasoning is hardest.

**Non-Goals:**
- No changes to any Ansible code — this change only edits `AGENTS.md` files.
- Not a full C4 model of every monorepo role; scope is the platform topology exercised by `tcharl.ansible_orchestration`.
- No diagram tooling (no mermaid/PlantUML dependencies) — plain ASCII in fenced code blocks so it renders in any terminal/editor.

## Decisions

**D1: Placement split between master and role AGENTS.md.**
`Practices` + L1/L2 C4 go into `ansible/roles/AGENTS.md` (master): practices are monorepo-wide, and the VM topology is shared context for every role in this platform. The L3 task-flow graph goes into `tcharl.ansible_orchestration/AGENTS.md` because it is role-internal; the master file gets a one-line pointer to it.
*Alternative considered:* everything in master — rejected, it would push orchestration-internal details into context that other roles' agents don't need.

**D2: Practices as a pattern→module table plus an exception rule.**
A short table mapping observed shell patterns to native equivalents (`touch` → `file state=touch`; `sed -i` → `replace`/`lineinfile`; `cat a b > c` → `slurp`+`copy content=`; polling loops → `uri /healthz` + `retries/until` or `wait_for`; cert field inspection → `community.crypto.x509_certificate_info`; kubectl get/list with explicit credentials → `kubernetes.core.k8s_info`). Followed by an explicit exception rule: when no native equivalent exists (chain validation via `openssl verify`, PEM→DER hashing for kubeadm discovery, `kubeadm reset`, `pkill`, kubectl auth embedded in a kubeconfig file), the shell task must carry a comment stating why.
*Alternative considered:* prose-only guidance — rejected; tables are faster to consult mid-task and match how the review notes were phrased.

**D3: Readiness-wait convention.**
Codify the agreed pattern: variabilize host/port/timeout (no hardcoded `localhost` literals in waits), then poll a real readiness endpoint (`uri https://<host>:6443/healthz` with `retries`/`until`) rather than raw port checks or fixed long timeouts. This comes from the user's clarification on the `wait_for` review notes.

**D4: No-dead-code rule.**
Every included task file must be referenced by an include/import; every registered variable must be consumed downstream. Rationale: this is exactly how `kube-install-refresh-join.yml` (orphaned, empty input var) and the redundant `/root/.kube/config` patch went unnoticed until review.

**D5: Diagram style.**
Plain ASCII in fenced code blocks, ≤ ~72 columns, box characters limited to `+`, `-`, `|`, arrows `-->`. Ports/paths in diagrams must match current task files; a diagram line that cannot be verified against code is not included.

## Risks / Trade-offs

- [Diagrams drift from reality as tasks evolve] → Keep diagrams small and fact-based (only ports/paths verifiable in `tasks/`); note in the section header that topology-affecting changes must update the diagram.
- [Practice table over-prescribes for roles with different needs] → Frame it as "default preference, exception allowed with comment" rather than a hard ban on shell.
- [AGENTS.md bloat reduces readability] → Cap each new section at ~40 lines; tables over prose; role file gets only the L3 graph + pointer.

## Migration Plan

Docs-only: edit `ansible/roles/AGENTS.md` and `tcharl.ansible_orchestration/AGENTS.md`, verify rendering, done. Rollback = git revert of the two files. No converge impact to test.

## Open Questions

None — placement (D1) and wait convention (D3) were confirmed with the user during exploration.
