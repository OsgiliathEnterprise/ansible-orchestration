# Proposal

## Why

During the `ticket-dedup-hygiene` parallels verification (2026-11-07) the post-swap
calico-node CA recovery gate failed with `calico-node CA recovery did not complete
(phase: rollout)`: a stale `calico-typha` replica starved confd on node2, so
`bird.cfg` was never rendered and the fresh `calico-node` pod stayed 0/1
(`bird: Unable to open configuration file /etc/calico/confd/config/bird.cfg`).
The existing escalation — deleting the stuck `calico-node` pods — is ineffective
against this failure mode: the recreated pod re-registers against the same
starved typha and wedges again. Manual recovery that worked (verified in-session,
fresh pod Ready in ~45s) was deleting both `calico-typha` replicas and the
`calico-kube-controllers` pod. The recovery automation should perform this
escalation itself instead of requiring manual unlocking of an automated script.

## What Changes

- `tasks/calico-ca-recovery.yml`: the escalation step (currently "delete calico-node
  pods stuck not-Ready") additionally deletes, before the stuck-node deletions:
  - all `calico-typha` pods in `calico-system` (label selector `k8s-app=calico-typha`)
  - the `calico-kube-controllers` pod (label selector `k8s-app=calico-kube-controllers`)
  Both additional deletions are discovery-driven and no-op when the workload is
  absent (typha-less or kube-controllers-less installs). The Deployment/ReplicaSet
  controllers recreate them; a fresh typha clears the stale confd watch cache, and
  recreated calico-node pods then render `bird.cfg` and reach Ready.
- `defaults/main.yml`: new `calico_recovery_restart_typha: true` toggle to opt out
  of the control-plane restart part of the escalation (stuck-pod deletion stays).
- Failure report: the escalation records that the typha restart fired, so the
  rescue evidence distinguishes "pod-deletion only" from "typha restart" attempts.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `ipa-pki-bootstrap`: new requirement — the post-swap CNI recovery escalates
  beyond calico-node pod deletion by restarting the Calico control plane
  (`calico-typha`, `calico-kube-controllers`) when calico-node pods remain stuck
  not-Ready, so converge self-heals the stale-typha confd-starvation flake
  without manual intervention.

## Impact

- `tasks/calico-ca-recovery.yml` (escalation section between the two readiness
  poll phases), `defaults/main.yml` (one new variable + comment).
- No changes to the trigger patch, poll budgets, rescue evidence schema, or the
  ticketing flow from `ticket-dedup-hygiene`; no new collections required.
- Docs: inline comments in the task file; the role AGENTS.md L3 graph line for
  `calico-ca-recovery.yml` stays valid (no new include files).
- Verification risk: the escalation only fires when phase 1 times out, so a green
  converge does not exercise it — the tasks include a fault-injection drill to
  validate the path on demand.
