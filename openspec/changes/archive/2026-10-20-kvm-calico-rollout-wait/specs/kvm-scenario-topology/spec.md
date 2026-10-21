# Spec Delta: kvm-scenario-topology

## ADDED Requirements

### Requirement: KVM scenario raises the workload rollout wait budget
The KVM scenario's converge playbook SHALL set `kubernetes_rollout_wait_timeout` to a value greater than the role default so that workload rollout waits (the calico-node DaemonSet rolling restart and the coredns rollout) can complete on the single-worker CI topology. The override SHALL be a play-level var in the KVM converge playbook, and `defaults/main.yml` SHALL remain unchanged.

#### Scenario: KVM converge resolves the scenario override
- **WHEN** the `kvm` scenario's converge playbook runs
- **THEN** `kubernetes_rollout_wait_timeout` resolves to the scenario override, not the role default

#### Scenario: Override stays scenario-local
- **WHEN** the KVM override is introduced
- **THEN** `defaults/main.yml` is unchanged and the variable is set only in `molecule/kvm/converge.yml`

### Requirement: Non-KVM scenarios retain the default rollout wait
The role default for `kubernetes_rollout_wait_timeout` SHALL remain 300, and the `default`, `parallels`, and `default_noreset_kube` scenarios SHALL resolve the role default without any scenario-level override.

#### Scenario: Non-KVM converge resolves the role default
- **WHEN** the `default`, `parallels`, or `default_noreset_kube` scenario's converge runs
- **THEN** `kubernetes_rollout_wait_timeout` resolves to 300
