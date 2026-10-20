# Tasks

## 1. KVM single-worker topology

- [x] 1.1 Remove the `node2.osgiliath.test` platform block from `molecule/kvm/molecule.yml` (keep the `idm`, `master`, `node1` platforms and all their `provider_options` untouched). Verify: the `kvm` scenario inventory lists exactly 3 platforms and the `kube_node` group contains only `node1.osgiliath.test`.
- [x] 1.2 Confirm the scenario plays are untouched and group-driven. Verify: `grep -rn "node2" molecule/kvm/` returns no match, and `molecule/kvm/converge.yml` / `molecule/kvm/prepare.yml` are unmodified in the diff.

## 2. Two-node test file

- [x] 2.1 Create `molecule/default/tests/test_two_node.py`: a self-contained `_worker_hosts()` helper (same `MOLECULE_INVENTORY_FILE` + `AnsibleRunner` pattern as `test_node.py`) and `test_two_workers_present()` — no `host` argument, no pytest marker, asserts `len(workers) >= 2` with a failure message naming the missing second worker. Verify: `flake8` is clean on the new file.
- [x] 2.2 Verify the guard semantics in both directions. Verify: with a two-worker inventory (e.g. `default`'s molecule inventory) the guard passes; with a single-worker inventory (a minimal temp INI with one `kube_node` host, run via `MOLECULE_INVENTORY_FILE=... pytest molecule/default/tests/test_two_node.py`) it fails fast with the clear message, proving fail-fast on a wrong topology.

## 3. Test mirroring (structural, by reference)

- [x] 3.1 Create the `molecule/kvm/tests/` directory with per-file symlinks: `conftest.py`, `test_master.py`, `test_node.py` → `../../default/tests/<name>`; no reference to `test_two_node.py`. Verify: `ls -l molecule/kvm/tests/` shows exactly those three symlinks resolving to the shared files, and no physical copies exist.
- [x] 3.2 Confirm `kvm` collection is exactly the linked subset. Verify: a testinfra-verifier-style collection (os.walk + `test_*.py` pattern from the role root, as molecule does) over `molecule/kvm/tests/` yields `test_master.py` and `test_node.py` only; `molecule/kvm/molecule.yml` has no `verifier.options` change in the diff.
- [x] 3.3 Create the `molecule/parallels/tests` directory symlink pointing to `../default/tests`. Verify: the symlink resolves and a collection over it yields all four files including `test_two_node.py`; `molecule/parallels/molecule.yml` is unmodified.

## 4. CI entry and documentation

- [x] 4.1 Align `.travis.yml` with the monorepo env: the `master` job runs `uv tool run --python 3.13 --with tox tox -e test-exec-monorepo -- --scenario-name kvm`. Verify: the command in `.travis.yml` matches, and `test-exec-monorepo` exists in `tox.ini` with `REQUIREMENTS_PATH=requirements-monorepo.yml`.
- [x] 4.2 Fix `AGENTS.md` Key Files: remove the stale `molecule/parallels/tests/test_converge.py` entry; add `molecule/default/tests/` as the shared suite source of truth and document the mirroring layout (per-file symlinks in `molecule/kvm/tests/` excluding `test_two_node.py`; directory symlink `molecule/parallels/tests` → `../default/tests`; convention: new shared test files are mirrored into `kvm/tests/` in the same change). Verify: every path listed under Key Files exists on disk, and the layout description matches the on-disk symlinks.
- [x] 4.3 Extend `AGENTS.md` VM topology with `kvm` (idm + master + node1, 3 VMs) and `default` (idm + master + node1 + node2, 4 VMs) rows. Verify: the table matches the platform blocks in each `molecule/*/molecule.yml`.

## 5. Integration verification

- [x] 5.1 Run `tox -e lint` and verify yamllint, flake8, and ansible-lint all pass.
- [ ] 5.2 Full two-worker cycle on the local host: destroy → converge → verify with `--scenario-name parallels`. Verify: the full suite (including the `test_two_node.py` guard) passes against the 4-VM stack.
- [ ] 5.3 Full single-worker KVM cycle (Linux host; otherwise let the Travis `master` job be the first run): destroy → converge → verify with `--scenario-name kvm`. Verify: 3 VMs converge, verify executes `test_master.py` + `test_node.py` only — verify log shows no `test_two_node.py` collection.
- [ ] 5.4 First CI run: `uv tool run --python 3.13 --with tox tox -e test-exec-monorepo -- --scenario-name=kvm` (Travis `master` job) completes green within `travis_wait 70`. Verify: the job log shows create/prepare/converge/verify all passing with the single-worker topology.
