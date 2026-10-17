# Tasks

## 1. Recovery task file (rolling calico-node DaemonSet restart)

- [x] 1.1 Create `tasks/calico-ca-recovery.yml` that detects the `calico-node` DaemonSet in `calico-system` and no-ops (skips, does not fail) when absent — verify with a dry-run on a host without Calico showing the skip, and `ansible-lint` passing
- [x] 1.2 Add a task to rolling-restart the `calico-node` DaemonSet via `kubectl -n calico-system rollout restart daemonset/calico-node`, gated on presence from 1.1 — verify after converge that every node has a Ready `calico-node` pod and no node is left `NotReady`

## 2. Readiness gate

- [x] 2.1 No separate operator-ready wait — after the rolling restart (1.2) the operator is neither recreated nor waited on; convergence is gated solely by the per-node `calico-node` readiness check (2.2), which directly encodes the goal (every node has working CNI)
- [x] 2.2 Add a per-node `calico-node` readiness wait that fails naming the affected node(s) on timeout — verify converge fails with node names when a node lacks a Ready `calico-node`

## 3. Wire into the swap

- [x] 3.1 Include `calico-ca-recovery.yml` at the end of `tasks/ipa-pki-swap.yml`, after the existing kubelet refresh + cluster-stabilization gates — verify the task graph runs recovery last and converge completes only after CNI is Ready on all nodes

## 4. Verification

- [x] 4.1 Re-run converge (`tox -e converge-monorepo --scenario-name=parallels`) and confirm both nodes report Ready, the operator is healthy, and a `calico-node` pod exists on every node — verified via clean destroy + reconverge; live check shows master + node1 `Ready` with a Ready `calico-node` on each
- [x] 4.2 Run molecule verify (`tox -e verify-monorepo --scenario-name=parallels`) and confirm the cluster end-state holds (both nodes Ready). Note: `test_node_ready_via_master_admin_conf` also has an independent pre-existing jsonpath bug (`.items[0]` on a single-object response) tracked separately — this change makes node1 actually Ready but does not fix that query. **Verified:** ran against the converged cluster → 38 passed / 1 failed; sole failure is `test_node_ready_via_master_admin_conf` (the documented pre-existing `.items[0]` bug, out of scope), while `test_kubectl_get_nodes_equals_two` + `test_tigera_operator_pods_running` pass — end-state holds.
