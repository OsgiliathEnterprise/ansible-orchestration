# Design: restart-resilience-verify

## Context

Molecule's testinfra verifier runs pytest against `molecule/default/tests/` (the parallels scenario symlinks its `tests/` dir there). `conftest.py` already derives hosts from `MOLECULE_INVENTORY_FILE` and skips everything when that env var is absent. The existing suite (`test_master.py`, `test_node.py`) has per-module `testinfra_hosts` declarations and several tests with built-in retry loops (tigera pods up to 3 min, PV Available up to ~10.8 min), but `test_kubectl_get_nodes_equals_two` asserts immediately with no retry.

Restarting `kubelet` on the master also restarts the API server / controller-manager / scheduler static pods (kubelet manages `/etc/kubernetes/manifests`), so a gate that restarts kubelet on both hosts exercises static-pod recovery and node re-registration in one pass — which is what "everything still works" means at service level.

## Goals / Non-Goals

**Goals:**
- Make kubelet-restart resilience the first action of the verify phase: all functional tests run against a post-restart state.
- Fail fast and clearly (host-named errors) when a host does not come back ready.
- Keep the change additive to the test harness — no changes to converge behavior required for the gate itself.

**Non-Goals:**
- Full VM reboot (explicitly out of scope per user decision: restarting kubelet is enough to ensure everything is working).
- Rebooting or restarting services on the IPA server (idm).
- Multi-node scale-out restart scenarios.

## Decisions

### D1: Restart gate lives in `conftest.py` as a session-scoped autouse fixture

An autouse, session-scoped pytest fixture in `molecule/default/tests/conftest.py` runs exactly once before any test in the session — literally "the first action before every test". It is a no-op when `MOLECULE_INVENTORY_FILE` is absent, matching the existing skip behavior.

Alternatives considered:
- **Separate `test_01_reboot*.py` module** (alphabetical ordering): fragile against future file additions that sort earlier; per-host parameterization makes coordinated two-host restart awkward.
- **Custom molecule verify playbook before pytest**: more invasive — changes verifier wiring in `molecule.yml`; the request is for a test-phase action, and the fixture keeps everything inside the existing harness.

### D2: Restart kubelet on both Kubernetes hosts simultaneously

Issue `systemctl restart kubelet` on master and node1 in one pass; the hosts stay up (no SSH drop), so no connection-recovery handling is needed. This covers "master or node" in a single strongest guarantee at service level, and keeps idm untouched.

Alternative considered: **full VM reboot** — rejected per user decision as out of scope for this change; a kubelet restart exercises the same recovery paths (static pods, node re-registration) at a fraction of the time cost (~1–2 min vs ~5–8 min).

### D3: Host objects built inside the fixture via AnsibleRunner

The `host` fixture is per-test/per-parameterized-host; a session fixture builds its own `Host` objects with `testinfra.utils.ansible_runner.AnsibleRunner(os.environ["MOLECULE_INVENTORY_FILE"]).get_hosts(...)` — the same mechanism conftest already uses for `pytest.testinfra_hosts`. The host list (master + node1 FQDNs, matching what the test modules hardcode) is overridable via a comma-separated `RESTART_HOSTS` env var so other scenarios can reuse the shared tests dir.

### D4: Single-phase readiness wait

Poll until BOTH conditions hold (~5 min budget, 30 × 10 s):
- each host's `kubelet` reports active (running) (`service kubelet status | grep -c 'active (running)'`)
- `kubectl get nodes` shows both nodes Ready (run from master)

One phase because the hosts never go down: SSH stays reachable throughout. The kubectl condition is what matters — restarting the master's kubelet restarts the API server static pod, so kubectl is briefly unavailable; and `test_kubectl_get_nodes_equals_two` has no retry loop, so the gate must guarantee nodes are Ready before releasing the suite. The existing tests' own retry loops then cover the rest (tigera operator, PV Available). A host that misses the readiness window fails verify with an error naming it.

### D5: "Everything still works" = the entire existing suite after the gate

No duplicated checks and no new assertions needed: `test_master.py` (~30 tests) and `test_node.py` run unchanged against the post-restart state — they already assert kubelet active on both hosts, 2 nodes in kubectl, API ports open, PV Available. If the end-to-end run reveals something that does not recover after a kubelet bounce, it is fixed in role tasks as follow-up work surfaced by verify (not part of this change's core).

## Risks / Trade-offs

- [Verify phase grows ~1–2 min] → trivial: only the verify phase is affected, not converge or idempotence.
- [Restarting master's kubelet drops the API server static pod mid-gate] → expected behavior; the readiness wait (nodes Ready) covers it before any functional test runs.
- [Cascade failures obscure root cause if the gate passes but something is broken] → the first failing test points at it; acceptable for CI diagnostics.

## Migration Plan

No user-facing migration — additive test-phase behavior only. Rollback = revert the conftest change (gate disappears, suite runs as-is).

## Open Questions

(none)
