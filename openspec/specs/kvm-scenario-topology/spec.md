# Kvm Scenario Topology

## Purpose

Defines the platform topology of the KVM molecule scenario: a single-worker CI setup that keeps the full-stack converge within the CI runner's budget, while two-worker coverage stays with the `default` and `parallels` scenarios.

## Requirements

### Requirement: KVM scenario defines exactly one worker
The KVM molecule scenario SHALL define exactly one `kube_node` platform (`node1.osgiliath.test`) in addition to the `ipaservers` platform (`idm.osgiliath.test`) and the `kube_master` platform (`master.osgiliath.test`). No second worker platform SHALL be defined in `molecule/kvm/molecule.yml`.

#### Scenario: Three-platform inventory
- **WHEN** the `kvm` scenario inventory is generated
- **THEN** it contains exactly the platforms `idm.osgiliath.test`, `master.osgiliath.test`, and `node1.osgiliath.test`
- **THEN** the `kube_node` group contains exactly `node1.osgiliath.test`

### Requirement: Two-worker topology is preserved in non-KVM scenarios
The `default` and `parallels` molecule scenarios SHALL continue to define exactly two `kube_node` platforms (`node1.osgiliath.test`, `node2.osgiliath.test`), so multi-worker coverage required by `kube-worker-scaling` is preserved outside CI.

#### Scenario: Default and parallels keep two workers
- **WHEN** the `default` or `parallels` scenario inventory is generated
- **THEN** the `kube_node` group contains exactly `node1.osgiliath.test` and `node2.osgiliath.test`

### Requirement: Scenario playbooks remain group-driven
Reducing the KVM scenario to one worker SHALL require no change to `molecule/kvm/converge.yml` or `molecule/kvm/prepare.yml`: all worker-facing targeting SHALL stay expressed against the `kube_node` group, so no playbook SHALL name `node2.osgiliath.test` as a target.

#### Scenario: No playbook change needed
- **WHEN** the `node2` platform is removed from `molecule/kvm/molecule.yml`
- **THEN** `molecule/kvm/converge.yml` and `molecule/kvm/prepare.yml` contain no edit and reference no literal worker hostname

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
