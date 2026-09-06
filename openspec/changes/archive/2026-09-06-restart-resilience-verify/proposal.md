# Proposal: restart-resilience-verify

## Why

The molecule verify phase only exercises the converged state as-is: nothing proves the cluster recovers when `kubelet` is restarted on master or node. A host where a `systemctl restart kubelet` leaves static pods down, the node stuck NotReady, or the API server unreachable is a silent failure mode — converge and idempotence both pass while the platform cannot survive routine service maintenance. We want verify to catch this by making kubelet-restart resilience the first thing tested.

## What Changes

- Add a **restart gate** to the molecule testinfra verifier: before any functional test runs, restart `kubelet` on the Kubernetes hosts (`master.osgiliath.test` and `node1.osgiliath.test`) simultaneously and wait for full readiness (kubelet active + both nodes Ready in kubectl). All existing tests in `test_master.py` / `test_node.py` then run against the post-restart state — so "everything still works" is asserted by the entire existing suite, not a separate copy of checks.

Non-goals: full VM reboot (explicitly out of scope per user decision — a kubelet restart is enough to ensure everything is working); rebooting the IPA server (idm); multi-node scale-out scenarios.

## Capabilities

### New Capabilities
- `restart-resilience`: verify-phase behavior around kubelet restart — the verifier restarts `kubelet` on all Kubernetes hosts before functional tests, waits for readiness, and asserts cluster-wide health after the restart.

### Modified Capabilities
(none — existing capability requirements are unchanged; their tests simply now run against a post-restart state)

## Impact

- `molecule/default/tests/conftest.py` (shared by the parallels scenario via symlink): session-scoped restart gate fixture, no-op when `MOLECULE_INVENTORY_FILE` is absent.
- No role task changes expected: a kubelet restart exercises existing systemd/static-pod behavior; if the end-to-end run reveals something that does not come back after a kubelet bounce, fix it in role tasks as follow-up work surfaced by verify.
- Verify phase duration grows by roughly 1–2 minutes (kubelet restart + node re-registration window) per scenario run.
