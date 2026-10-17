# Tasks

## 1. Reorder and validate the node-join gate

- [x] 1.1 In `tasks/kube-install-join-node.yml`, move the FreeIPA `kubernetesNodes` profile gate, the CA fetch (delegated to idm), the CA slurp, and the CA install (`/etc/kubernetes/pki/ca.crt`) to the top of the join block, ahead of the API readiness gate; the profile gate must precede the CA fetch. Verify: `ansible-playbook --syntax-check` passes and the task order inside the `when: not kube_node_joined` block matches the design D1 sequence (profile gate → CA fetch → CA install → validated gate → drop-in surgery → cert request → conf → kubelet → k8s_info).
- [x] 1.2 Replace the liveness-only readiness gate with the validated one: `uri` on `https://{{ orchestration_master_ip }}:6443/healthz` with `ca_path: /etc/kubernetes/pki/ca.crt`, `status_code: 200`, `retries: 40`, `delay: 5`, `until: api_server_ready.status == 200`; remove `validate_certs: no` and rename the task to reflect validated readiness. Verify: `ansible-playbook --syntax-check` passes and `grep -c 'validate_certs' tasks/kube-install-join-node.yml` returns 0.
- [x] 1.3 Update the file's header comment: readiness signal 1 becomes "the API server is reachable and its serving certificate validates against the node's IPA-derived trust anchor"; note that the profile + CA existence signal now precedes the CA fetch. Verify: the header comment's two-signal statement matches the implemented order.

## 2. Integration verification (parallels scenario)

- [x] 2.1 Run a full cycle (`tox -e destroy` then `tox -e converge-monorepo`, `--scenario-name=parallels`); verify the node joins through the validated gate: the "wait for API server readiness (validated)" task is OK, and the node appears in the cluster via the `k8s_info` assertion.
- [x] 2.2 Run `tox -e verify-monorepo` (`--scenario-name=parallels`); verify all testinfra tests pass with the node joined under its `system:node:<hostname>` identity.
- [ ] 2.3 Re-run `tox -e converge-monorepo` (`--scenario-name=parallels`) without destroy; verify the join block is skipped on the already-joined node (`/etc/kubernetes/kubelet.conf` exists) and converge stays green.
