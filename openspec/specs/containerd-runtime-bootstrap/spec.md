# containerd-runtime-bootstrap Specification

## Purpose

Guarantees that the CRI runtime the kube bring-up tasks talk to is always the daemon running the role-deployed `/etc/containerd/config.toml`: the config write and the containerd restart form one atomic unit from the play's perspective, so fresh installs never hand `kubeadm` a daemon serving a stale configuration while steady-state converges stay change-free.

## Requirements

### Requirement: Containerd daemon runs the role-deployed configuration before kube bring-up
The role SHALL guarantee that, once `Fix Requirements | Deploy containerd configuration` reports a change, the `containerd` service has been restarted with the deployed `/etc/containerd/config.toml` before any later task in the same play interacts with the CRI runtime (CRI facts, `kubeadm init`, `kubeadm join`). The restart SHALL be triggered by flushing the `containerd` refresh handler immediately after the deploy task, not deferred to end of play.

#### Scenario: Fresh install serves the deployed configuration
- **WHEN** a freshly provisioned host converges and the containerd configuration task writes a new `/etc/containerd/config.toml`
- **THEN** containerd is restarted before `kubeadm init` / `kubeadm join` runs
- **AND** `kubeadm` preflight connects to the CRI v1 runtime API successfully (no `unknown service runtime.v1.RuntimeService`)

#### Scenario: Steady state keeps zero-change converge
- **WHEN** the derived configuration already matches the deployed `/etc/containerd/config.toml`
- **THEN** the deploy task reports `changed=false`, no handler is queued
- **AND** the flush task is a no-op and the host reports no change for the containerd tasks

### Requirement: Worker join reaches the profile gate dependency
Because the master's `kubeadm init` must succeed for the `kubernetesNodes` certificate profile to be created, a converged cluster SHALL reach worker join without the profile-readiness gate exhausting its retry budget on a healthy control plane.

#### Scenario: Workers join after master bring-up
- **WHEN** the role converges a fresh master and worker topology
- **THEN** the master's `kubeadm init` succeeds on first attempt
- **AND** workers observe the `kubernetesNodes` profile within the gate's retry budget and join the cluster
