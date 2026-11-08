# Design

## Context

`tasks/calico-ca-recovery.yml` runs on the master after the IPA PKI swap (called
from `ipa-pki-swap.yml`). Its current flow is: all-nodes Ready gate → patch the
`calico-node` DaemonSet with a CA-fingerprint `restartedAt` trigger → poll phase 1
(`calico_recovery_rollout_retries` x `..._delay`, `ignore_errors: true`) → name
stuck pods → delete stuck pods (the escalation) → poll phase 2 (budget failure
routes into the rescue evidence report and final fail).

Observed flake (parallels verification, 2026-11-07): a `calico-typha` replica
holds a stale watch cache; confd inside the fresh `calico-node` pod logs
"Skipping confd config file", never renders `/etc/calico/confd/config/bird.cfg`,
and BIRD dies with `Unable to open configuration file`. Deleting the stuck pod
reproduces the wedge because the recreated pod re-registers against the same
starved typha. Deleting both `calico-typha` replicas plus the
`calico-kube-controllers` pod cleared it: the recreated calico-node pod reached
Ready in ~45s (within one poll phase budget of 18x10s).

Constraints:
- The escalation must stay inside the existing block/rescue (its failure routes
  into the evidence collector; the collector must not be broken).
- The recovery must remain a no-op when Calico is absent, and the new steps must
  be no-ops when typha/kube-controllers are absent (typha-less installs).
- Native `kubernetes.core` modules only (monorepo practice); no shell kubectl.
- Idempotence: tasks must not report spurious changes on a re-converge where the
  CA is unchanged (the whole recovery block no-ops in that case, so escalation
  tasks never run — but they still must be structured so the file stays lint- and
  static-gate-clean, e.g. every registered variable consumed).

## Goals / Non-Goals

**Goals:**
- Converge self-heals the stale-typha confd-starvation flake without manual
  `kubectl delete pod` intervention.
- The escalation remains targeted: it fires only when phase 1 timed out and
  pods are actually stuck.
- Keep the opt-out granular: the typha/kube-controllers restart can be disabled
  independently of the stuck-pod deletion.

**Non-Goals:**
- No restart of the tigera/calico operator (deliberately avoided since earlier:
  forces image re-pull, destabilises a healthy control plane — see the file
  header comment).
- No change to the trigger patch, the poll budgets, the all-nodes Ready gate, or
  the rescue evidence schema (beyond one extra fact in the failure message).
- No general-purpose "watch confd health" detection during normal (non-recovery)
  converges — this only hardens the recovery path.

## Decisions

### T1 — Restart typha + kube-controllers in the same escalation step, before deleting stuck pods
The escalation becomes: (1) discover and delete `calico-typha` pods
(`k8s-app=calico-typha`), (2) discover and delete the `calico-kube-controllers`
pod (`k8s-app=calico-kube-controllers`), (3) delete stuck `calico-node` pods,
then poll phase 2 as today.
- Deleting the control-plane pods *before* the stuck-node pods means recreated
  calico-node pods register against a fresh typha on their first attempt,
  instead of burning half the phase-2 budget on a second wedge-then-restart
  cycle. (Ordering is tolerant — confd retries its typha connection — but the
  measured 45s recovery only happened with the control plane restarted first.)
- Alternative considered: escalate only after phase 2 also times out (two-tier
  escalation). Rejected: it doubles the worst-case stall (another full 18x10s
  budget) before applying the proven fix, and requires a third poll phase.
- Alternative considered: always restart typha on every CA recovery. Rejected:
  a healthy typha restart churns the confd feed for the whole cluster; it must
  stay a failure-path action.

### T2 — Discovery via `k8s_info` + label selector, delete by name loop
Both restarts use `kubernetes.core.k8s_info` with `namespace: calico-system` and
the label selectors above, then a `kubernetes.core.k8s: state: absent` loop over
the discovered names (same shape as the existing stuck-pod deletion, including
`wait: false`).
- Why not `k8s` with `label_selectors` + `state: absent` in one task: the
  delete-by-selector path is less explicit about what was removed for the
  failure report, and the existing file already establishes the
  discover-then-delete-by-name pattern.
- Discovery runs only when the escalation fires (same `when:` as the current
  escalation: phase 1 failed and stuck pods exist — except that pods may be
  missing rather than stuck; the task guard is `calico_rollout_pods.failed`,
  matching phase 2's condition, so a missing-pod stall also gets the typha
  restart). Empty discovery list → loop skipped → no-op, satisfying the
  typha-less scenario.
- Registered variables `calico_typha_pods` / `calico_controllers_pods` are
  consumed by both the delete loops and the escalation-fired fact (T4), so the
  static gate's unused-register check stays green.

### T3 — One toggle `calico_recovery_restart_typha: true` (defaults/main.yml)
Gates the two control-plane delete loops (and their discovery tasks) only;
stuck-pod deletion is unconditional as today. A single boolean rather than two
(typha vs controllers) because the measured recovery needs both and they are
useless apart; the scenario requirement covers them as one action.

### T4 — Record escalation depth for the failure report
A `set_fact` after the restart loops records
`calico_recovery_escalation: typha-restart` (vs `pod-delete` when opted out or
nothing found); the final fail message interpolates it
(`escalation: {{ calico_recovery_escalation | default('none') }}`) so operators
can tell which escalation ran. Kept as a plain string fact — no new evidence
structure, so the existing nested-rescue collector is untouched.

### T5 — Deletion without waiting; rely on phase 2 poll
`wait: false` on all new delete tasks: the Deployment/ReplicaSet controllers
recreate typha replicas and the controller pod asynchronously; phase 2's
calico-node readiness poll is the effective barrier (a Ready calico-node
requires a serving typha, since confd must have rendered `bird.cfg`). No new
typha-readiness poll task: it would add a budget to tune for no observable
benefit over the calico-node gate.

## Risks / Trade-offs

- [Deleting kube-controllers transiently pauses cluster-wide IPAM/policy
  reconciliation] → Acceptable: it only fires on an already-stuck recovery path,
  the controller recreates in seconds, and the alternative is a failed converge
  with the same workloads already down.
- [Both typha replicas deleted at once briefly removes the confd feed for
  healthy calico-node pods too] → confd caches its last rendered config and
  reconnects on restart; the window is bounded by pod recreation (~10-20s
  measured), far below the wedge this fixes.
- [Escalation fires on stalls whose cause is NOT typha (e.g. broken image)] →
  The extra restarts are wasted work but harmless (self-healing controllers);
  phase 2 still fails with the existing per-pod evidence, so diagnosis is not
  degraded.
- [Escalation path is not exercised by a green converge] → Mitigated by the
  fault-injection drills in tasks.md, executed via the ad-hoc harness (see
  *Drill recipe* below); additionally exercised **live** by a natural
  stale-typha flake on the verification converge (self-healed via
  `typha-restart`, ~50 s).

## Drill recipe (validated 2026-11-07, parallels)

Deterministic reproduction of the stale-typha wedge, ~2 min per run:

1. Harness: an ad-hoc playbook that `include_tasks` the REAL
   `tasks/calico-ca-recovery.yml` against the live master with the same vars
   converge provides (`kube_config_path: /etc/kubernetes/admin.conf`, group
   names, budgets; `-e drill_restart_typha|drill_rollout_retries|drill_rollout_delay`
   overrides). Inventory points at the molecule VMs with molecule's own keys
   (`~/.cache/molecule/<role>/parallels/.vagrant/machines/<host>/parallels/private_key`,
   user `vagrant`) — same auth molecule uses, no new credentials.
2. Freeze the typha replicas on their current hosts (check placement first with
   `kubectl get pods -n calico-system -o wide`):
   `sudo kill -STOP $(pgrep -f "[/]usr/bin/calico-typha")` — the bracket in the
   pattern keeps `pkill`-style self-matching from freezing the ssh session
   itself (observed: `pkill -STOP -f /usr/bin/calico-typha` matched its own
   `sudo` parent). Unfreeze with `kill -CONT` on the same pids; frozen pods
   stuck in `Terminating` need `kill -CONT` to let kubelet finish teardown.
3. Delete the calico-node pods (`-l k8s-app=calico-node --wait=false`) so the
   replacements need a fresh confd feed, then run the harness within ~10 s.

Caveats learned during drilling:
- **Liveness race**: typha has a liveness probe (`/liveness`, period 60,
  failureThreshold 3), so a SIGSTOP-frozen typha is killed by kubelet on its
  own after ~3-4 min and the wedge self-heals. The escalation must be reached
  within that window — keep the phase-1 budget short (`drill_rollout_retries`
  4-10 × delay 10) and start the harness immediately after injection.
- **iptables block of 5473 from the pod CIDR does not work**: calico-node runs
  `hostNetwork`, so its confd connects from the *node* IP and a
  `-s <podCIDR> --dport 5473 -j DROP` rule never matches (verified: pods came
  up Ready with the rule installed).
- A single fresh stuck pod is enough to exhaust phase 1 (the poll requires
  every non-terminating calico-node pod Ready), so freezing the typha replicas
  plus deleting one calico-node pod reproduces the wedge.

## Migration Plan

Additive task-file change plus one new default; no state migration. Rollback =
revert the task-file/defaults commit, or set
`calico_recovery_restart_typha: false` to restore pre-change escalation
behavior without reverting.
