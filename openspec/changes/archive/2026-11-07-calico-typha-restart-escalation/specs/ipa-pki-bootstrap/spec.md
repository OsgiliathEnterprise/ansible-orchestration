# Spec Delta

## ADDED Requirements

### Requirement: Stuck calico-node pods escalate to a Calico control-plane restart
When `calico-node` pods remain stuck not-Ready after the first readiness poll
following the post-swap restart trigger, the recovery escalation SHALL restart
the Calico control plane in `calico-system` (`calico-typha`,
`calico-kube-controllers`) before deleting the stuck pods, then re-poll
readiness. The restart SHALL be label-discovered (no-op when absent) and
disableable via `calico_recovery_restart_typha` without disabling the
stuck-pod deletion.

#### Scenario: Stale-typha confd starvation self-heals
- **WHEN** a `calico-node` pod stays not-Ready because its confd never renders
  `bird.cfg` (starved by a stale `calico-typha` replica) and the first
  readiness poll exhausts its budget
- **THEN** the escalation deletes the `calico-typha` and `calico-kube-controllers`
  pods so their controllers recreate them with a fresh watch cache
- **THEN** the escalation deletes the stuck `calico-node` pods
- **THEN** a Ready `calico-node` pod is present on every node before converge
  completes, with no manual intervention

#### Scenario: Typha absent (single-node or typha-less install)
- **WHEN** the escalation fires and no pod matches the `calico-typha` or
  `calico-kube-controllers` label selectors
- **THEN** the control-plane restart step is a no-op
- **THEN** the stuck-pod deletion still proceeds

#### Scenario: Control-plane restart opted out
- **WHEN** a scenario sets `calico_recovery_restart_typha` to `false`
- **THEN** the escalation deletes only the stuck `calico-node` pods
- **THEN** the second readiness poll and the failure-evidence behavior are
  unchanged

#### Scenario: Green converge does not touch the control plane
- **WHEN** the first readiness poll succeeds (all `calico-node` pods Ready)
- **THEN** no `calico-typha` or `calico-kube-controllers` pod is deleted

#### Scenario: Escalation outcome in failure evidence
- **WHEN** the escalation (control-plane restart and pod deletions included)
  still leaves a `calico-node` pod not-Ready within the second poll budget
- **THEN** converge fails with the existing structured evidence
- **THEN** the report records whether the Calico control-plane restart fired,
  distinguishing a pod-deletion-only attempt from a full escalation
