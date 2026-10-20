# Design

## Context

See `proposal.md` — Why. Current state that shapes the approach:

- All four scenarios (`default`, `default_noreset_kube`, `kvm`, `parallels`) define the same 4-VM topology (idm + master + node1 + node2).
- Only `molecule/default/tests/` contains tests (`conftest.py`, `test_master.py`, `test_node.py`). `kvm` and `parallels` have no `tests/` dir, so molecule's testinfra verifier logs `Skipping, no tests found` — their `verify` phase is a silent no-op.
- The suite is already inventory-driven: `test_node.py` sets `testinfra_hosts = _worker_hosts()` (the `kube_node` group), and every topology-sensitive assertion in `test_master.py` derives expectations from `MOLECULE_INVENTORY_FILE`. No test hardcodes a 2-node expectation.
- Converge/prepare plays and role tasks target `kube_master,kube_node` groups only — no literal worker hostnames.
- CI runs the `kvm` scenario through `uv tool run --python 3.13 --with tox tox -e test-exec-monorepo -- --scenario-name=kvm` (`molecule test` full sequence) under `travis_wait 70`; `.travis.yml` currently names the standalone env (`test-exec`), which the entry must be aligned to.

## Goals / Non-Goals

**Goals:**

- `kvm` scenario converges a 3-VM single-worker stack (idm + master + node1), cutting CI converge cost.
- `kvm` and `parallels` `verify` phases actually execute the shared suite (no more no-op), with `kvm` running the node-count-agnostic subset via structural (filesystem-level) exclusion.
- Two-worker assertions have an explicit home (`test_two_node.py`) and a fail-fast guard.
- Zero test duplication: one source of truth, mirrored by reference.

**Non-Goals:**

- No change to the role's runtime tasks, defaults, or converge/prepare plays (group-driven by construction).
- No new cross-node functional tests (pod-to-pod connectivity across `nodeName`s, NFS RWX PV consumed from a non-master worker) — deferred follow-up.
- `default_noreset_kube` untouched (two workers, no tests).
- The in-flight `mgmt_attach: false` rollback and the stale `kvm-scenario-network` spec are a separate change; this change does not touch `provider_options` beyond removing the `node2` platform block.

## Decisions

### D1: Drop the `node2` platform block instead of parameterizing the scenario

Molecule scenario YAML is static per scenario; the vagrant driver's platform schema has no env-var-driven platform lists. Deleting the platform block is the idiomatic, minimal change, and the converge comment already documents the contract: *"Targeting group unions means adding a worker is a molecule.yml-only change"* (removing one is the same).

### D2: The suite stays in `molecule/default/tests/`; scenarios mirror by reference

Per user decision, the source of truth stays in `molecule/default/tests/` (owned natively by the `default` scenario, whose verifier dir is its own `tests/`). Mirroring:

- `molecule/kvm/tests/` — a **directory** of **per-file symlinks**: `conftest.py`, `test_master.py`, `test_node.py` → `../../default/tests/<name>`. `test_two_node.py` is deliberately absent.
- `molecule/parallels/tests` — a **directory symlink** to `../default/tests` (full suite, no exclusions).

Verified mechanics (against the installed molecule 24.x source):

- `Testinfra._get_tests` walks `self.directory` with `os.walk(followlinks=True)`. For `kvm`, the directory exists and its per-file symlinks (to files) appear in the `files` list; the `test_*.py` pattern matches their names. For `parallels`, the symlinked directory is followed and the shared files are found.
- Test paths are relative to the invocation cwd (role root) and pytest runs with `cwd=scenario.directory`, where `molecule/kvm/tests/test_*.py` resolves through the symlinks.
- `conftest.py` is auto-discovered from the mirrored dir; each test file is self-contained (each defines its own `_worker_hosts()`), so no shared helper module is needed.

Alternatives considered:

- **`verifier.additional_files_or_dirs: [../default/tests/*]`** — rejected: `glob` cannot descend through the non-existent `molecule/kvm/tests/` intermediate dir (verified: the glob returns `[]`), so it silently yields zero tests.
- **Physical copies** — rejected: duplication drift, contrary to the repo's no-dead-code ethos.
- **Whole-dir symlink for `kvm` too** — rejected by user decision: the two-worker file must not run under the single-worker scenario, and the exclusion should be structural (file presence), visible in the directory listing.

### D3: Structural exclusion instead of a `pytest -m` marker expression

A marker-based exclusion (`verifier.options: {m: not two_node}`, verified to bake into `pytest -m` via `dict2args`) was designed and rejected in favor of filesystem-level exclusion: CI runs the suite through `molecule test` (via `tox -e test-exec-monorepo`), and the user's requirement is that `kvm` simply does not reference `test_two_node.py`. Consequences:

- No `two_node` pytest marker anywhere — the file name and its guard document the multi-worker requirement.
- No `verifier.options` change in `molecule/kvm/molecule.yml`.
- **Mirror-drift trade-off (accepted):** a new node-count-agnostic test file added to `molecule/default/tests/` is NOT automatically mirrored into `molecule/kvm/tests/` (per-file symlinks). Mitigation: spec requirement "Future shared tests are mirrored explicitly" + an AGENTS.md note naming the convention. `parallels` (whole-dir symlink) stays drift-proof by construction.

### D4: Guard-only initial content for `test_two_node.py`

The file starts with exactly one test — the topology guard:

- `test_two_workers_present()`: no `host` parameter (it asserts on the inventory, not host state), reads the `kube_node` group via the `MOLECULE_INVENTORY_FILE` runner (same pattern as `test_node.py`), asserts `len(workers) >= 2` with a message naming the missing second worker.
- `>= 2`, not `== 2`: future-proof if a scenario ever scales to 3 workers.

The guard doubles as a canary: if the file is ever run against a single-worker inventory (e.g. someone mirrors it into `kvm/tests/` by mistake), it fails fast with an actionable message. Outside molecule, `conftest.py`'s `pytest_runtest_setup` skips the whole run (`MOLECULE_INVENTORY_FILE` absent), so the guard only runs under a real scenario.

Cross-node functional tests (pod-to-pod connectivity across `nodeName`s) are a follow-up change.

### D5: `.travis.yml` entry alignment

CI's entry for this change is `tox -e test-exec-monorepo -- --scenario-name=kvm` (monorepo env: local roles resolved from the monorepo via `REQUIREMENTS_PATH=requirements-monorepo.yml`). `.travis.yml` currently names the standalone env (`test-exec`) — a one-line alignment so the committed CI entry matches the actual execution path.

### D6: Docs fold into this change

`AGENTS.md` (role): the Key Files entry `molecule/parallels/tests/test_converge.py` is stale (file no longer exists — the suite consolidated into `molecule/default/tests/`). The VM topology table (currently "parallels scenario" only) gains `kvm` (3 VMs) and `default` (4 VMs) rows, and the mirroring mechanism (per-file symlinks for `kvm`, directory symlink for `parallels`) gets a line so the layout is discoverable and the mirror convention is documented.

## Risks / Trade-offs

- [First real `verify` run surfaces stale failures] The `kvm`/`parallels` verify phases have never executed the suite; the first run may hit tests that drifted since `default` last ran them. → Mitigation: run the full `parallels` cycle locally before the CI run; the `kvm` CI run is the second verification, not the first.
- [Mirror drift] A new shared test file silently skips the `kvm` mirror (per-file symlinks). → Mitigation: spec requirement for same-change mirroring + AGENTS.md convention note.
- [`travis_wait 70` budget] `verify` now adds suite time (readiness polls exit early on healthy clusters; worst case ~3 min per polling test). → Mitigation: 3 VMs instead of 4 cut converge time; if the budget still overruns, split the Travis job (`molecule test --test-sequence`) as a follow-up — no spec impact.
- [Symlink portability] Symlinks are git-native and packaging-safe (verified: hatchling wheel packages only `meta/`; sdist includes only role content dirs — `molecule/` is excluded from both). → Residual risk: unusual copy/extract tooling that dereferences symlinks materializes a copy; acceptable for this repo's toolchain (git, ansible-galaxy, tox, molecule).
- [Guard as canary only] With structural exclusion, nothing prevents someone from mirroring `test_two_node.py` into `kvm/tests/` — the guard then fails loudly on the single-worker inventory. → Accepted: loud failure is the desired behavior (fail fast, actionable message).

## Migration Plan

No runtime impact: molecule scenario files, test files, symlinks, `.travis.yml`, and `AGENTS.md` only. Single-branch change.

1. Lint gate: `tox -e lint` (yamllint, flake8, ansible-lint).
2. Inventory check: `molecule`-generated inventory for `kvm` lists 3 platforms; `default`/`parallels` list 4.
3. Collection check: the `kvm` verifier collects exactly `test_master.py` + `test_node.py`; `parallels` collects all four files including `test_two_node.py`.
4. Two-worker path locally (macOS): full `parallels` cycle — destroy → converge → verify — full suite including the `two_node` guard.
5. Single-worker path: full `kvm` cycle on a Linux host (or let the Travis `master` job be the first KVM run): destroy → converge → verify — 3 VMs, `test_two_node.py` not collected.
6. Rollback: revert the commit — remove both symlinks, restore the `node2` block, delete `test_two_node.py`, revert `.travis.yml`. Independent of the in-flight `mgmt_attach` rollback.

## Open Questions

None blocking. Deferred explicitly: cross-node functional tests in `test_two_node.py` (pod-to-pod connectivity across `nodeName`s; NFS RWX PV consumed from a non-master worker) — a follow-up change after the baseline is green.
