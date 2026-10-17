## Purpose

Defines how the cluster scales to an arbitrary number of worker nodes: every worker converges in a single pass, joins independently with its own identity, and is exercised by molecule scenarios and tests.

## ADDED Requirements

### Requirement: Role converges an arbitrary number of worker nodes
The role SHALL converge any number of hosts assigned to the `kube_node` group in a single pass, driven entirely by group membership rather than a hardcoded host list. No task SHALL reference a specific worker hostname as its target.

#### Scenario: Multi-worker single-pass convergence
- **WHEN** inventory contains two or more hosts in the `kube_node` group
- **THEN** all of them converge within one play and each reaches a healthy, joined state without any task naming a particular worker

#### Scenario: No hardcoded worker reference
- **WHEN** role tasks are audited for worker targeting
- **THEN** every worker-facing operation is expressed against the `kube_node` group (or per-host facts), with no literal single-worker hostname remaining as a target

### Requirement: Each worker joins independently with its own identity
Each worker SHALL request its own per-node certificate and register with the API server as `system:node:<hostname>`. A worker's join SHALL be gated on control-plane readiness rather than on play ordering, so workers may join in any order.

#### Scenario: Independent per-worker join
- **WHEN** multiple workers are present and the control plane becomes ready
- **THEN** each worker independently requests its own node certificate and joins, without depending on another specific worker's completion

#### Scenario: All workers registered with distinct identities
- **WHEN** convergence of N workers completes
- **THEN** `kubectl get nodes` reports all N workers, each identified by its own hostname as a `system:node:<hostname>` identity

### Requirement: Molecule scenarios and tests exercise multiple workers
At least one molecule scenario SHALL define two or more worker platforms, and the node test suite SHALL run against every worker host in the inventory rather than a fixed single-host list.

#### Scenario: Multi-worker scenario coverage
- **WHEN** a molecule scenario is defined with ≥2 worker platforms
- **THEN** its converge targets all of them and its tests assert health for each worker, not only `node1`
