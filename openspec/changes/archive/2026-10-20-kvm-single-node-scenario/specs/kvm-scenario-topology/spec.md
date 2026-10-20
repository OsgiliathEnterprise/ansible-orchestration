# Kvm Scenario Topology

## Purpose

Defines the platform topology of the KVM molecule scenario: a single-worker CI setup that keeps the full-stack converge within the CI runner's budget, while two-worker coverage stays with the `default` and `parallels` scenarios.

## ADDED Requirements

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
