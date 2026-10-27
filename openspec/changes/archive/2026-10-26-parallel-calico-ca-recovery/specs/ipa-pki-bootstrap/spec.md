## MODIFIED Requirements

### Requirement: Pre-existing Calico/Tigera workloads trust the post-swap CA
After the PKI swap replaces `/etc/kubernetes/pki/ca.crt` and restarts
control-plane static pods, the system SHALL restart the pre-existing
`calico-node` DaemonSet in `calico-system` so each node re-materializes the
post-swap in-cluster CA. The restart SHALL update
`updateStrategy.rollingUpdate.maxUnavailable` from
`calico_recovery_max_unavailable` in the same patch as the
CA-fingerprint-based trigger. The default value is `100%`; a serial `1` value
remains selectable per scenario. The trigger SHALL run only when the workload
does not reflect the current post-swap CA.

#### Scenario: calico-node pods refreshed after swap
- **WHEN** the PKI swap has completed, control-plane components report Ready,
  and the current CA fingerprint differs from the template's `restartedAt`
  annotation
- **THEN** the system patches the annotation and selected update strategy so
  each pod mounts the post-swap in-cluster CA
- **THEN** a Ready `calico-node` pod is present on every node before converge
  completes

#### Scenario: Default parallel recovery
- **WHEN** a multi-node cluster uses the default recovery strategy
- **THEN** the DaemonSet reports `maxUnavailable: 100%`
- **THEN** the pods are replaced concurrently rather than in a strict
  one-at-a-time order

#### Scenario: Serial recovery is selectable
- **WHEN** a scenario sets `calico_recovery_max_unavailable` to `1`
- **THEN** the DaemonSet reports `maxUnavailable: 1`
- **THEN** the pods are replaced one at a time

#### Scenario: Recovery is idempotent
- **WHEN** converge runs again with an unchanged post-swap CA
- **THEN** the patch is a no-op and no `calico-node` pod is replaced

#### Scenario: CA rotation re-triggers recovery
- **WHEN** the post-swap CA changes after a previous recovery
- **THEN** the workload restarts again to consume the new CA

#### Scenario: Calico is absent
- **WHEN** no `calico-node` DaemonSet exists in `calico-system`
- **THEN** recovery is skipped
- **THEN** the system does not create a DaemonSet

### Requirement: Converge waits for per-node CNI readiness after swap
After triggering the `calico-node` restart, the system SHALL wait for a Ready
pod on every node. On timeout it SHALL fail with structured evidence:
the nodes lacking a Ready pod (or an all-nodes-covered marker), DaemonSet
generation and observed-generation values, desired/updated/ready counts, and
one line for every non-Ready pod containing its node, phase, Ready-condition
message, and latest Event reason and message.

#### Scenario: calico-node deployed to all nodes
- **WHEN** the rolling restart has completed after the swap
- **THEN** a `calico-node` pod exists and is Ready on each node (master and
  workers) before converge completes

#### Scenario: CNI not ready in time
- **WHEN** a `calico-node` pod has not become Ready on some node within the
  readiness timeout
- **THEN** converge fails with an error naming the affected node or nodes
- **THEN** the error includes the required structured evidence

#### Scenario: Controller lag
- **WHEN** the rollout times out and `status.observedGeneration` is behind
  `metadata.generation`
- **THEN** the failure report displays both values so controller lag is
  distinguishable from stalled pod initialization

#### Scenario: Pod initialization fails
- **WHEN** a non-Ready `calico-node` pod has a CNI or image-pull Event
- **THEN** the failure identifies its node, phase, Ready-condition message,
  and latest Event reason and message

#### Scenario: Failure evidence contains partial objects
- **WHEN** a referenced pod, Event, or DaemonSet status field is absent
- **THEN** the failure report uses an explicit placeholder for that field
- **THEN** evidence collection does not replace the rollout timeout with a
  template error
