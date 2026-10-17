# Tasks

## 1. Provision the kubeclusteradm CA (CA #2) on the IPA server

- [x] 1.1 Add `ipa_kubeclusteradm_ca_name: "kubeclusteradm"` to `defaults/main.yml`.
- [x] 1.2 Create `tasks/ipa-kubeclusteradm-ca.yml` mirroring `ipa-kubernetes-ca.yml` for CA #2 using the same **shell** `ipa` commands (the installed `freeipa.ansible_freeipa` v1.17.0 has no `ipa_ca`/`ipa_ca_acl` modules): create the `kubeclusteradm` CA via `ipa ca-add` (delegated to idm, subject `CN=kubeclusteradm,O=<domain upper>`), create its CA ACL via `ipa caacl-add kubeclusteradm-acl --usercat=all`, link CA #2 to the ACL via `ipa caacl-add-ca`, and link the global `kubeAdministrators` and `kubernetesNodes` profiles to the CA #2 ACL via `ipa caacl-add-profile`. No DNS A+PTR (CA #2's cert has no IP SANs).
- [x] 1.3 Include `ipa-kubeclusteradm-ca.yml` from `tasks/ipa-certs.yml` immediately after `ipa-kubernetes-ca.yml`, so CA #2 exists before any client cert request.
- [x] 1.4 Grant CA #2 ACL access to all cluster hosts in `tasks/ipa-cert-renewal.yml` (master-only, delegated to idm): a shell `caacl-show` membership check followed by per-host `caacl-add-host {{ ipa_kubeclusteradm_ca_name }}-acl` over `groups[idm_group] + groups[kube_masters_group] + groups[kube_nodes_group]`, mirroring the CA #1 grant loop — host-principal renewals (front-proxy as `host/<master>`, node-client as `host/<node>`) are rejected by `usercat=all` alone.

## 2. Sign client certificates from CA #2

- [x] 2.1 In `tasks/ipa-front-proxy.yml`, change the front-proxy client cert request `ca` from `{{ ipa_kubernetes_ca_name }}` to `{{ ipa_kubeclusteradm_ca_name }}` (profile stays `kubeAdministrators`).
- [x] 2.2 In `tasks/kube-apiserver-kubelet-client.yml`, change the kubelet client cert request `ca` from `{{ ipa_kubernetes_ca_name }}` to `{{ ipa_kubeclusteradm_ca_name }}` (profile stays `kubeAdministrators`).
- [x] 2.3 In `tasks/kube-node-cert.yml`, change the node client cert request `ca` from `{{ ipa_kubernetes_ca_name }}` to `{{ ipa_kubeclusteradm_ca_name }}` (profile stays `kubernetesNodes`).
- [x] 2.4 In `tasks/admin-user.yml`, change the admin cert request `ca` from `{{ ipa_kubernetes_ca_name }}` to `{{ ipa_kubeclusteradm_ca_name }}` (profile stays `kubeAdministrators`).
- [x] 2.5 Leave `tasks/ipa-api-server.yml` (serving cert) on `{{ ipa_kubernetes_ca_name }}` (CA #1).
- [x] 2.6 ~~Leave the kubeadm-generated **controller-manager** and **scheduler** client certs on CA #1~~ **REVISED**: the investigation found those certs are signed by the **kubeadm CA (CA #0)**, not CA #1 — they are untrusted by the new two-CA bundle. Re-issue both from CA #2 via static-subject profiles (see section 7; design D3a).

## 3. Rebuild the client CA bundle as the two-CA bundle

- [x] 3.1 In `tasks/ipa-certs.yml`, add a task to fetch the `kubeclusteradm` (CA #2) CA cert to the master (delegated to idm via `ipa-getcert`), install it at `/etc/kubernetes/pki/ca.crt.kubeclusteradm`, and slurp it.
- [x] 3.2 In `tasks/ipa-certs.yml`, change the client CA bundle task to build `ca-bundle.crt` from the `kubeclusteradm` (CA #2) + `kubernetes-ca` (CA #1) CA certs (replacing the previous kubeadm + `kubernetes-ca` composition).
- [x] 3.3 Update the bundle task's name/comment to reflect the two-CA composition.

## 4. Update header comments

- [x] 4.1 Update the `tasks/ipa-certs.yml` header comment to describe the two-CA model (CA #1 = serving/trust anchor, CA #2 = client certs, bundle = CA #2 + CA #1).

## 5. Renewal path and molecule tests (two-CA model)

Discovered during implementation: the renewal script and the molecule tests still encode the single-CA model.

- [x] 5.1 Update `templates/kube-cert-renew.sh.j2`: `request()` takes the issuing CA as a parameter; the apiserver serving cert renews from `kubernetes-ca` (CA #1), the client certs (front-proxy, cluster-admin, node-client) renew from `{{ ipa_kubeclusteradm_ca_name }}` (CA #2) — the CA that issued them.
- [x] 5.2 Update `molecule/parallels/tests/test_master.py` for the two-CA model: the client-cert issuer assertions (admin issuer/signed, apiserver-kubelet-client, front-proxy-client) target `kubeclusteradm` (CA #2); the serving-cert assertion stays on `kubernetes-ca` (CA #1); add a test asserting `/etc/kubernetes/pki/ca-bundle.crt` holds exactly two certificates — `kubeclusteradm` (CA #2) first, then `kubernetes-ca` (CA #1).
- [x] 5.3 Update `molecule/parallels/tests/test_node.py` for the two-CA model: `test_node_client_cert_signed_by_kubeclusteradm_ca` targets `kubeclusteradm` (CA #2); `test_cert_renewal_forced_eligibility_extends_node_client` additionally asserts the re-issued node client cert is CA #2-issued.
- [x] 5.4 Anchor the `ipa-certs.yml` API-restart gate to a three-CA file (`ca.crt.kubeadm` + CA #2 + CA #1, built from slurped content) instead of `ca-bundle.crt` — the old-cert window (kubeadm-signed serving cert before the swap) is no longer covered by the two-CA bundle (D4).

## 6. Control-plane client cert re-issue (discovered during implementation)

The investigation found the controller-manager and scheduler client certs are signed by the
**kubeadm CA (CA #0)**, not CA #1: they are untrusted by the new two-CA bundle, so the
`ipa-pki-swap` gates and the admin `kubectl get nodes` verification fail (their kubeconfigs
carry the CA #0-issued admin cert while `admin-user.yml` — which re-issues it from CA #2 —
runs after `ipa-pki-swap`). Design D3a/D4 were revised accordingly.

- [x] 6.1 Create static-subject certificate profiles `kubeControllerManager` (subject `CN=system:kube-controller-manager, O=system:masters`) and `kubeScheduler` (subject `CN=system:kube-scheduler, O=system:masters`) in `tasks/ipa-kubernetes-ca.yml`, mirroring the `kubernetesNodes` profile block (existence check, template dump from `caIPAserviceCert`, `lineinfile` patches of `profileId`/`visible`/subject, `certprofile-import`), and link both to the CA #2 ACL in `tasks/ipa-kubeclusteradm-ca.yml` (mirroring the existing `caacl-add-profile` tasks).
- [x] 6.2 Create `tasks/ipa-controlplane-clients.yml` (master, included from `tasks/ipa-certs.yml` after `kube-apiserver-kubelet-client.yml`): per component (controller-manager, scheduler) — generate a key + clientAuth CSR (CN = master hostname, mirroring `ipa-front-proxy.yml`), request from CA #2 with the static-subject profile via `ipacert` (principal `host/<master>`), install key/cert at `/etc/kubernetes/pki/controller-manager-client.{crt,key}` and `/etc/kubernetes/pki/scheduler-client.{crt,key}`, re-embed the credentials into `controller-manager.conf` / `scheduler.conf` via `kubectl config set-credentials` (base64-embedded — the scheduler static pod mounts only its conf), and restart the two static pods (manifest move pattern from the renewal script).
- [x] 6.3 Reorder `tasks/main.yml`: run `ipa-kube-admin-credential.yml` → `admin-user.yml` **before** `ipa-pki-swap.yml`, and move the `kubectl get nodes` verification task from `tasks/ipa-kube-admin-credential.yml` to the end of `tasks/admin-user.yml` (after the `admin.conf` re-embed) so the pki-swap gates authenticate with the CA #2 admin cert.
- [x] 6.4 Update `templates/kube-cert-renew.sh.j2`: add controller-manager and scheduler entries (renew from `{{ ipa_kubeclusteradm_ca_name }}` with the static-subject profiles, re-embed into the conf files, restart the static pods), mirroring the existing entries.
- [x] 6.5 Update `molecule/parallels/tests/test_master.py`: assert the controller-manager and scheduler client certs are CA #2-issued with the exact `system:masters` subjects (`O=system:masters`, clientAuth EKU).
- [x] 6.6 Update the L3 task-flow graph in the role `AGENTS.md` (new `ipa-controlplane-clients.yml`, reordered includes).

## 7. Integration verification (parallels scenario)

- [x] 7.1 Run a full cycle (`tox -e destroy` then `tox -e converge-monorepo`, `--scenario-name=parallels`); verify the `kubeclusteradm` CA is created on idm, the CA #2 ACL contains all four hosts (idm, master, node1, node2), the client certs are CA #2-signed (including the re-issued controller-manager and scheduler client certs), and the bundle is CA #2 + CA #1. (Executed: destroy OK, converge OK on idm/master/node1/node2; CA #2 present on idm, ACL covers all four hosts, node client certs CA #2-issued per testinfra, master bundle inspected as CA #2 + CA #1.)
- [x] 7.2 Run `tox -e verify-monorepo` (`--scenario-name=parallels`); verify all testinfra tests pass (admin `kubectl` works, node joins, API server serves with the CA #1 serving cert, KCM lease is fresh, scheduler is Ready). (Executed: 66/66 tests pass on both nodes.)

## 8. ipaservice resolvability race (found during 7.1 re-run)

The full-cycle re-run failed in `tasks/ipa-api-server.yml`: the SAN-alias `ipaservice`
task (`HTTP/kubernetes-svc.<domain>`, `HTTP/kubernetes-master.<domain>`) died with
"Host ... does not have corresponding DNS A/AAAA record". Root cause: the `ipaservice`
pre_callback runs `util.verify_host_resolvable(hostname)` (skipped only by `force`),
which resolves the name through the **IPA server host's system resolver**, not the IPA
zone database. The idm link's `resolvectl` races the IPA DNS servers (authoritative,
answer `10.96.0.1`/master IP) against `8.8.8.8` (NXDOMAIN for `*.osgiliath.test`);
whichever answers first is adopted and cached for the negative-cache TTL (~2 min), so
service creation is flaky per cache window even though the A records exist in the zone
(verified: `dig @10.211.55.66` returns the records; `dig`/`getent` on idm flip between
answer and NXDOMAIN across cache windows). `skip_host_check: True` skips only the
`host_show` lookup, not the resolvability check.

- [x] 8.1 Add `force: True` to the SAN-alias `ipaservice` task in `tasks/ipa-api-server.yml` (with an explanatory comment): the invariant the check guards ("hostname has an A record in the zone") is enforced earlier by `ipa-kubernetes-ca.yml` (A+PTR records for `kubernetes-svc`/`kubernetes-master`); `force` skips only the resolvability check. Matches the sibling `HTTP/<master>` task, which already uses `force: True`.
- [x] 8.2 Re-run the full cycle (`tox -e destroy` → `tox -e converge-monorepo` → `tox -e verify-monorepo`, `--scenario-name=parallels`); re-covers 7.1–7.2. (Executed with the `force: True` fix in place; converge clean on all four hosts, 66/66 tests pass.)

## 9. Master kubelet client cert wiring (found during 7.1/8.2 verification)

The full-cycle re-run got past `calico-ca-recovery` only to fail its rollout gate: the master
node was stuck `NotReady` after the swap. The master's kubelet log showed `Unable to register
node with API server: Unauthorized` on every API call: `/etc/kubernetes/kubelet.conf` still
pointed `client-certificate`/`client-key` at the kubeadm-CA-signed
`/var/lib/kubelet/pki/kubelet-client-current.pem`, which the two-CA client bundle
(`ca-bundle.crt` = CA #2 + CA #1) no longer trusts. The CA #2-signed
`apiserver-kubelet-client.{crt,key}` existed on disk but was never wired into `kubelet.conf`.
Node kubelets were unaffected: `kube-install-join-node.yml` generates their kubeconfig directly
with `client-certificate: /etc/kubernetes/pki/node-client.crt`. Design D6 documents the fix.

- [x] 9.1 In `tasks/kube-apiserver-kubelet-client.yml`, re-point `/etc/kubernetes/kubelet.conf` `client-certificate` and `client-key` at the CA #2-signed `apiserver-kubelet-client.{crt,key}` (two `replace` tasks; idempotent — `replace` only reports changed when the line differs).
- [x] 9.2 In `tasks/ipa-pki-swap.yml`, restart the master kubelet after the swap (gated on the `apiServerOverride` block change so a re-converge does not churn it) and gate on the master node reporting Ready before `calico-ca-recovery` runs — a calico-node pod on a `NotReady` node can never be Ready, so the DaemonSet rollout gate would time out on the master.
- [x] 9.3 In `tasks/kube-apiserver-kubelet-client.yml`, remove the kubeadm bootstrap mechanism from the master's kubelet unit (the package drop-in `10-kubeadm.conf` carries `--bootstrap-kubeconfig`; with `rotateCertificates: true` the kubelet bootstraps a client cert signed by the original kubeadm CA, which the two-CA bundle does not trust — the node stays `NotReady` after the swap). Write a clean `20-orchestration.conf` (kubelet.conf only, no bootstrap, no rotation, pinned `--node-ip`), disable `rotateCertificates` in `config.yaml`, and remove the `/var/lib/kubelet/pki` store and the orphaned `bootstrap-kubelet.conf`. Gate the kubelet restart on the unit/credential tasks reporting a change (no churn on re-converge). Design D7.
- [x] 9.4 Re-run the full cycle (`tox -e destroy` → `tox -e converge-monorepo` → `tox -e verify-monorepo`, `--scenario-name=parallels`); verify the master node is Ready post-swap and every node's calico-node pod is Ready (re-covers 7.1–7.2 and 8.2). (Executed with the 9.1–9.3 kubelet wiring in place; converge clean, 66/66 tests pass including `test_node_ready_via_master_admin_conf` and `test_calico_pods_ready`.)
