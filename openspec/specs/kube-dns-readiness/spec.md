# Kube DNS Readiness

## Purpose

After CNI installation on the master, ensure the cluster DNS workload (`coredns` in `kube-system`) is restarted using an explicit admin kubeconfig — never relying on ambient `KUBECONFIG` or a default kubeconfig path that may not exist yet — and that converge waits for the DNS rollout to complete before subsequent tasks proceed.

## Requirements

### Requirement: Cluster DNS workload is restarted after CNI installation
After the CNI install completes on the master, the system SHALL restart the cluster DNS deployment (`coredns` in `kube-system`) using an explicit admin kubeconfig and context — never relying on ambient `KUBECONFIG` or a default kubeconfig path that may not exist yet. The restart trigger value SHALL be tied to the installed CNI version so that re-converge at an unchanged CNI version performs no action.

#### Scenario: Fresh install triggers DNS restart
- **WHEN** the role runs on a master after CNI installation and the DNS deployment carries no restart marker for the current CNI version
- **THEN** the DNS deployment is restarted using an explicit admin kubeconfig and context

#### Scenario: Re-converge at unchanged CNI version is a no-op
- **WHEN** converge runs again and the DNS deployment already carries the restart marker for the current CNI version
- **THEN** the DNS workload is not restarted and reports no change

### Requirement: Converge waits for DNS rollout completion
After triggering the DNS restart, the system SHALL wait until the DNS deployment reports a fully rolled-out state (all desired replicas available and observed generation current) before subsequent converge tasks proceed. If the rollout does not complete within the configured timeout, converge SHALL fail with an explicit error identifying the DNS deployment — it SHALL NOT be swallowed as a best-effort failure.

#### Scenario: Rollout completes in time
- **WHEN** the DNS restart has been triggered and all desired replicas become available before the timeout
- **THEN** subsequent converge tasks proceed against the rolled-out DNS deployment

#### Scenario: Rollout does not complete in time
- **WHEN** the DNS rollout has not completed within the configured timeout
- **THEN** converge fails with an error identifying the DNS deployment
