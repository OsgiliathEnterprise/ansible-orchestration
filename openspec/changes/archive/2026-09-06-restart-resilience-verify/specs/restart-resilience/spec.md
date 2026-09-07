# restart-resilience (delta)

## Purpose

Guarantees that the converged cluster survives a kubelet restart: the molecule verify phase restarts `kubelet` on all Kubernetes hosts before running functional tests, waits for full readiness, and asserts cluster-wide health after the restart.

## ADDED Requirements

### Requirement: Verifier restarts kubelet on all Kubernetes hosts before functional tests
The molecule testinfra verifier SHALL restart the `kubelet` service on every Kubernetes host (master and node) as the first action of the verify phase, before any functional test executes. The restart gate SHALL be a no-op when pytest runs outside molecule (no `MOLECULE_INVENTORY_FILE`), preserving the existing skip behavior.

#### Scenario: Restart gate runs first
- **WHEN** the verify phase starts under molecule
- **THEN** `kubelet` is restarted on both Kubernetes hosts before any functional test in `test_master.py` or `test_node.py` executes

#### Scenario: No-op outside molecule
- **WHEN** pytest is invoked without `MOLECULE_INVENTORY_FILE` set
- **THEN** the restart gate does not run and tests are skipped as before

### Requirement: Verifier waits for full readiness after kubelet restart
After issuing the kubelet restart, the verifier SHALL wait until each host's `kubelet` service reports active (running) AND both nodes report Ready in `kubectl get nodes` before proceeding to functional tests. If readiness is not reached within the timeout, verify SHALL fail with an explicit error identifying the affected host(s).

#### Scenario: Cluster recovers after kubelet restart
- **WHEN** `kubelet` has been restarted on all Kubernetes hosts
- **THEN** each host's `kubelet` reports active (running)
- **THEN** `kubectl get nodes` shows both nodes Ready before functional tests start

#### Scenario: Readiness not reached in time
- **WHEN** the cluster has not become ready within the readiness timeout
- **THEN** verify fails with an error naming the host(s) that did not recover

### Requirement: Functional suite runs against post-restart state
After the restart gate completes, all existing functional tests SHALL run against the post-restart state and pass: `kubectl get nodes` reports both nodes Ready, `kubelet` is active on master and node1, API server ports are open in firewalld, and NFS-backed PVs reach Available.

#### Scenario: Cluster healthy after kubelet restart
- **WHEN** the restart gate has completed for all hosts
- **THEN** `kubectl get nodes` reports 2 nodes with both Ready
- **THEN** `kubelet` is active (running) on master and node1
- **THEN** the NFS-backed PV transitions to Available
