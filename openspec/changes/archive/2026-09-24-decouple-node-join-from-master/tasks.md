## 1. Validation spike (go/no-go gate for the rest)

- [x] 1.1 Add `kubernetesNodes` certificate profile creation + CA ACL link to the IPA infra tasks, with subject template `CN=system:node:$request.req_subject_name.cn$, O=system:nodes` (the profile adds the `system:node:` prefix so the CSR only needs a hostname-matching CN); verify `ipa certprofile-find | grep -c ': kubernetesNodes'` returns `1`, the profile is linked via `ipa caacl-show kubernetes-ca-acl`, and `ipa certprofile-show kubernetesNodes --out -` shows the prefixed template.
- [x] 1.2 On one worker, request a per-node certificate with `O=system:nodes`, `CN=system:node:<hostname>` via `ipacert` (`ca=kubernetes-ca`, `profile_id=kubernetesNodes`) and place it under `/etc/kubernetes/pki/`; verify the issued cert subject reads `O=system:nodes, CN=system:node:<hostname>` (`openssl x509 -noout -subject`).
- [x] 1.3 Point that worker's kubelet at the per-node cert + IPA CA and start it; verify `kubectl get node <hostname>` succeeds on the control plane and the node authenticates as `system:node:<hostname>` in group `system:nodes` (e.g. inspect the Node object / `kubectl auth can-i --as=system:node:<hostname>`). **This is the gate — do not proceed to groups 2–5 until it passes.**

## 2. Per-node certificate task (formalize)

- [x] 2.1 Create `tasks/kube-node-cert.yml`: per-node private key + CSR carrying **`CN=<hostname>`** (matching the host principal) + `O=system:nodes`, and an `ipacert` request (`ca=kubernetes-ca`, `profile_id=kubernetesNodes`, `principal=host/<h>`) — the profile template adds the `system:node:` prefix so the *issued* cert is `CN=system:node:<hostname>`; verify the CSR CN equals `<hostname>` (not `system:node:<h>`) and a re-run reports no change when the node cert already exists.

## 3. Node trust anchor from IPA

- [x] 3.1 Add a task that fetches `/etc/kubernetes/pki/ca.crt` on each worker directly from the FreeIPA `kubernetes-ca` (delegated to the IDM host), replacing the copy-from-master; verify the node's `ca.crt` SHA256 fingerprint matches the IPA `kubernetes-ca` certificate.

## 4. Rewrite the join mechanism

- [x] 4.1 In `tasks/kube-install-join-node.yml`, replace the master `admin.conf`/`kubeadm.crt`/`kubeadm.pem` copy with a constructed per-node `/etc/kubernetes/kubelet.conf` (own cert/key + IPA CA + `https://<master>:6443`); verify no task copies the master's `admin.conf`, `kubeadm.crt`, or `kubeadm.pem` onto a worker.
- [x] 4.2 Add a readiness gate before configuring kubelet credentials: wait until `https://<api>:6443/healthz == 200` **and** the `kubernetes-ca` exists in FreeIPA; verify the join retries until both conditions hold rather than failing on first attempt.
- [x] 4.3 Remove the now-dead copy-from-master tasks from the node join path; verify a content search shows no remaining master-slurp (`delegate_to: ... kube_masters_group`) for credential/CA copying inside `kube-install-join-node.yml`.
- [x] 4.4 Re-point the "wait for node to appear" verification in `kube-install-join-node.yml` from master's `admin.conf` (delegated) to the node's own `/etc/kubernetes/kubelet.conf` run on the worker (`kubectl get node <hostname> --kubeconfig /etc/kubernetes/kubelet.conf`); verify it succeeds before `ipa-pki-swap` runs and no longer delegates to the master.

## 5. Single-pass, order-tolerant converge

- [x] 5.1 Convert `molecule/parallels/converge.yml` from two sequential plays (master then node) to a single pass over `[master, node1]`; verify the playbook runs both hosts in one play and worker package/CRI/firewall/NFS prep is not gated on master post-processing.
- [x] 5.2 Apply the same single-pass form to `molecule/default/converge.yml` and `molecule/kvm/converge.yml`; verify none of the scenario converge files contain a separate master-then-node play pair.

- [x] 5.3 Fix the scheduler crash-loop introduced by re-pointing kubeconfigs at the IPA CA: the scheduler's static pod does not mount `/etc/kubernetes/pki`, so a `certificate-authority:` file reference in `scheduler.conf` crashes it at boot ("unable to read certificate-authority ... no such file or directory") and leaves every unscheduled pod (CNI DaemonSets included) stuck Pending. Embed the IPA CA as `certificate-authority-data` in `scheduler.conf` instead (kubeadm convention; other confs keep file references — KCM's static pod mounts pki, kubelet/admin confs are host-side); add a scheduler-Ready gate to `ipa-pki-swap.yml` symmetric with the KCM lease gate so converge fails loudly rather than passing with a dead scheduler.

## 6. Tests

- [x] 6.1 Extend `molecule/default/tests/test_node.py`: assert the node client certificate subject is `O=system:nodes`/`CN=system:node:<hostname>` and that the worker does not carry the master's admin cert; verify the test passes on a converged node.
- [x] 6.2 Confirm existing master tests (`molecule/default/tests/test_master.py`) still pass unchanged; verify `tox -e verify-monorepo -- --scenario-name=parallels` is green for the master assertions. (39/39 passed. Note: `test_scheduler_conf_references_ipa_ca` was rewritten as `test_scheduler_conf_embeds_ipa_ca` per task 5.3 — it previously asserted the file-reference form that crash-loops the scheduler.)

## 7. End-to-end verification

- [x] 7.1 Run the full cycle via tox on the parallels scenario (`destroy` → `converge-monorepo` → `verify-monorepo`); verify the node registers as `system:node:<hostname>`, the cluster is healthy, and record converge wall-clock time against the two-play baseline to confirm the ordering change did not regress it. (2026-09-23: destroy 54s; converge-monorepo ~23 min wall incl. VM creation — single pass over both hosts, `failed=0` on master and node1; verify-monorepo 39/39 passed. Node registered as `system:node:node1.osgiliath.test` (RBAC check confirms it can read only its own Node object); both nodes Ready; scheduler/KCM stable with no crash-loop. No two-play baseline wall-clock was recorded in this change's artifacts, so the ~23 min figure is recorded here as the single-pass reference.)
