# Proposal

## Why

CI runs the `kvm` molecule scenario via `uv tool run --python 3.13 --with tox tox -e test-exec-monorepo -- --scenario-name=kvm` — four VMs (idm + master + node1 + node2) — under `travis_wait 70`, and the two-worker setup strains the constrained runner (each extra worker adds VM creation, IPA enrollment, node join, drain/reset, and an extra NFS client). Compounding the problem, `verify` is a **silent no-op** in the `kvm` and `parallels` scenarios (they have no `tests/` directory; molecule logs "Skipping, no tests found"), so CI converges a full stack while asserting nothing.

## What Changes

- `molecule/kvm` scenario: drop the `node2.osgiliath.test` platform — the KVM scenario becomes a single-worker setup (idm + master + node1); `default` and `parallels` keep the two-worker topology.
- Introduce `molecule/default/tests/test_two_node.py`: tests that require ≥2 workers live here, starting with a topology guard that fails fast when the file runs against a single-worker inventory. No pytest marker — exclusion from the single-worker scenario is **structural**: the file is simply not mirrored.
- `molecule/kvm/tests/` becomes a directory of **per-file symlinks** to the shared suite — every `test_*.py` file **except** `test_two_node.py` (plus `conftest.py`). No `verifier.options` changes: molecule's testinfra verifier walks `molecule/kvm/tests/` and collects exactly the linked files.
- `molecule/parallels/tests` becomes a **directory symlink** to `../default/tests` — the full shared suite including `test_two_node.py` (two-worker scenario, no exclusions).
- No existing test moves: `test_master.py` and `test_node.py` are already inventory-driven (node-count agnostic) and run unmodified under every scenario.
- `.travis.yml`: reconcile the CI entry with the monorepo env — the CI command is `tox -e test-exec-monorepo -- --scenario-name=kvm` (current file says `test-exec`, the standalone env).
- `AGENTS.md`: fix the stale Key Files entry (`molecule/parallels/tests/test_converge.py` no longer exists) and document the mirroring layout (per-file symlinks for `kvm`, directory symlink for `parallels`).

## Capabilities

### New Capabilities

- `kvm-scenario-topology`: The KVM molecule scenario defines a single-worker topology (idm + master + exactly one `kube_node`) for CI, leaving the two-worker topology to the `default` and `parallels` scenarios.
- `molecule-test-mirroring`: The node-count-agnostic test suite has a single source of truth in `molecule/default/tests/`; scenarios mirror it by reference (symlinks), never by copy. `kvm` mirrors per-file, excluding the multi-worker file; `parallels` mirrors the whole directory. Tests requiring ≥2 workers live in `test_two_node.py` with a fail-fast guard.

### Modified Capabilities

(None — `kube-worker-scaling`'s "at least one scenario with ≥2 workers" requirement stays satisfied by `default` and `parallels`.)

## Impact

- `molecule/kvm/molecule.yml` — `node2` platform removed. No verifier options change.
- `molecule/kvm/tests/` — new directory of per-file symlinks (`conftest.py`, `test_master.py`, `test_node.py` → `../../default/tests/...`); `test_two_node.py` deliberately absent.
- `molecule/parallels/tests` — new directory symlink → `../default/tests`.
- `molecule/default/tests/test_two_node.py` — new file (worker-count guard; no marker).
- `.travis.yml` — CI entry aligned to `test-exec-monorepo`.
- `AGENTS.md` — Key Files correction + mirroring layout documentation.
- Out of scope (flagged): the working tree currently rolls back `mgmt_attach: false` in `molecule/kvm/molecule.yml` while `openspec/specs/kvm-scenario-network/spec.md` still mandates it — a separate spec-update change must follow that rollback. `default_noreset_kube` is untouched (two workers, no tests).
