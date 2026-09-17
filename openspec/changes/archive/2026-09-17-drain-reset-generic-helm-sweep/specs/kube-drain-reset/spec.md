## Purpose

Define the behavior of the Kubernetes destroy/drain path: every helm release present in the cluster is uninstalled before nodes are drained, so no chart's PodDisruptionBudgets can block the drain, without hard-coding any chart name.

## ADDED Requirements

### Requirement: All helm releases are uninstalled before node drain
The destroy/drain path SHALL uninstall every helm release present in the cluster, across all namespaces, before draining any node.

#### Scenario: Releases in multiple namespaces are swept
- **WHEN** the cluster contains helm releases in `istio-system` and `calico-system`
- **THEN** all of those releases are uninstalled before the node drain task runs

#### Scenario: No releases is a no-op
- **WHEN** the cluster contains no helm releases
- **THEN** the uninstall step performs no action
- **THEN** the destroy path proceeds to the node drain unchanged

### Requirement: The sweep is derived from live cluster state
The set of releases to uninstall SHALL be discovered from the cluster's live helm release records, including releases that are not in `deployed` status. No release name SHALL be hard-coded in the drain path.

#### Scenario: A previously unknown chart is swept without task changes
- **WHEN** a scenario installs a helm chart that no task names explicitly
- **THEN** the destroy path uninstalls it without any task modification

#### Scenario: A half-installed chart is swept
- **WHEN** a helm release is in `failed` status
- **THEN** the destroy path attempts its uninstallation

#### Scenario: Already-uninstalled entries are skipped
- **WHEN** a helm release record is in `uninstalled` status
- **THEN** the destroy path does not attempt to uninstall it again

### Requirement: The helm CLI is available on the master
The destroy path SHALL ensure a `helm` CLI is installed on the master node before running the sweep, installing it when absent.

#### Scenario: CLI installed when absent
- **WHEN** the master has no `helm` binary
- **THEN** the destroy path installs it before the discovery and uninstall tasks run

#### Scenario: Existing CLI is not reinstalled
- **WHEN** the master already has a `helm` binary
- **THEN** the destroy path does not download or replace it

### Requirement: CLI installation failure is fatal, sweep failure is not
A failure to install the helm CLI SHALL fail the destroy path. A failure of the discovery or uninstall steps (e.g. API unreachable) SHALL NOT abort the destroy path, consistent with the destroy path's tolerant convention.

#### Scenario: CLI installation fails
- **WHEN** the helm CLI download or installation fails
- **THEN** the destroy path fails

#### Scenario: API unreachable during the sweep
- **WHEN** the helm list or uninstall step cannot reach the API
- **THEN** the step is reported as non-fatal
- **THEN** the destroy path continues to the node drain

### Requirement: Uninstallation does not wait for resource teardown
Uninstalling a release SHALL NOT block on finalizers or resource deletion, because the destroy path tears down the nodes immediately afterwards.

#### Scenario: Slow-finalizer release does not stall the path
- **WHEN** a release's resources have finalizers that take time to clear
- **THEN** the uninstall step does not wait for them
- **THEN** the destroy path proceeds to the node drain

### Requirement: Destroy path ordering is preserved
The helm sweep SHALL run before the node drain, and the node drain SHALL run before node-object deletion and `kubeadm reset`, as before.

#### Scenario: Ordering on the master
- **WHEN** the destroy path runs on the first master
- **THEN** the helm sweep completes (or is reported) before the `k8s_drain` task
- **THEN** the `k8s_drain` task runs before node-object deletion and `kubeadm reset`
