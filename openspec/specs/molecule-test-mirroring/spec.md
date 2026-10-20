# Molecule Test Mirroring

## Purpose

Defines how the testinfra suite is shared across molecule scenarios: one source of truth in `molecule/default/tests/`, mirroring by reference (symlinks) instead of copy, and structural exclusion — a scenario's `tests/` directory simply does not contain the files it does not run.

## Requirements

### Requirement: The node-count-agnostic suite is the single source of truth
The shared testinfra suite (`conftest.py`, `test_master.py`, `test_node.py`, `test_two_node.py`) SHALL live exclusively in `molecule/default/tests/`. No scenario SHALL contain physical copies of suite files: scenarios mirror by reference only.

#### Scenario: No physical copies anywhere
- **WHEN** the repository is inspected
- **THEN** `test_master.py` and `test_node.py` exist as regular files only inside `molecule/default/tests/`
- **THEN** every occurrence of these names in `molecule/kvm/tests/` and `molecule/parallels/tests/` is a symlink resolving to `molecule/default/tests/`

### Requirement: The KVM scenario mirrors per-file, excluding the multi-worker file
`molecule/kvm/tests/` SHALL be a directory containing per-file symlinks to `molecule/default/tests/` for `conftest.py` and every node-count-agnostic test file (`test_master.py`, `test_node.py`), and SHALL NOT contain any reference (symlink or file) to `test_two_node.py`. No pytest marker expression or `verifier.options` change is used for this exclusion.

#### Scenario: KVM collects only the linked files
- **WHEN** the `kvm` scenario's `verify` phase runs the testinfra verifier
- **THEN** the collected test files are exactly `test_master.py` and `test_node.py` (resolved through `molecule/kvm/tests/` symlinks)
- **THEN** `test_two_node.py` is not collected and not executed

#### Scenario: Future shared tests are mirrored explicitly
- **WHEN** a new node-count-agnostic test file is added to `molecule/default/tests/`
- **THEN** a per-file symlink to it is added to `molecule/kvm/tests/` in the same change

### Requirement: The parallels scenario mirrors the full directory
`molecule/parallels/tests` SHALL be a directory symlink to `../default/tests`, so the `parallels` scenario (two workers) runs the complete shared suite including `test_two_node.py`, with no exclusions.

#### Scenario: Full suite runs under parallels
- **WHEN** the `parallels` scenario's `verify` phase runs the testinfra verifier
- **THEN** `test_master.py`, `test_node.py`, and `test_two_node.py` are all collected from `molecule/default/tests/`

### Requirement: The two_node file guards its own preconditions
`molecule/default/tests/test_two_node.py` SHALL contain a guard test that asserts the molecule inventory's `kube_node` group contains at least two hosts, so the file fails fast when executed against a topology that does not meet its preconditions. The guard SHALL read the inventory (not a host) and SHALL NOT require a `host` argument.

#### Scenario: Guard fails fast on a single-worker inventory
- **WHEN** `test_two_node.py` is executed against an inventory whose `kube_node` group contains exactly one host
- **THEN** the guard test fails with a message identifying the missing second worker

#### Scenario: Guard passes on a two-worker inventory
- **WHEN** `test_two_node.py` is executed under the `default` or `parallels` scenario
- **THEN** the guard test passes

### Requirement: Node-count-agnostic tests stay unchanged
Existing suite files (`test_master.py`, `test_node.py`) SHALL NOT be moved or split: they remain inventory-driven (node-count agnostic) and run unmodified under every scenario that mirrors them.

#### Scenario: Shared files run under all mirroring scenarios
- **WHEN** the `kvm`, `default`, or `parallels` scenario's `verify` phase runs
- **THEN** `test_master.py` and `test_node.py` are collected and executed in all three
