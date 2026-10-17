# Design: two-CA FreeIPA model for the Kubernetes cluster

## Context

Today the master's PKI is a three-file layout:

| File | Content | Used by |
|------|---------|---------|
| `ca.crt` | `kubernetes-ca` CA (IPA sub-CA) | `certificate-authority` in kubeconfigs (cluster trust anchor) |
| `ca.crt.kubeadm` | retained kubeadm CA | `--cluster-signing-cert-file` (controller-manager) |
| `ca-bundle.crt` | kubeadm CA + `kubernetes-ca` CA | `--client-ca-file` (API server), `--root-ca-file` (controller-manager, scheduler), scheduler embedded `certificate-authority-data` |

All certs (serving + client) are signed by the single `kubernetes-ca` CA.

## Decisions

### D1: CA #1 stays the cluster trust anchor; CA #2 signs client certs

- `CA #1 = kubernetes-ca` — signs **only** the API server serving cert (`apiserver.crt`). Its
  cert remains `/etc/kubernetes/pki/ca.crt` (the cluster trust anchor). Unchanged.
- `CA #2 = kubeclusteradm` (new) — signs all **client** certs:
  - front-proxy client (`front-proxy-client.crt`)
  - kubelet client (`apiserver-kubelet-client.crt`)
  - per-node client (`node-client.crt`, `system:node:<hostname>`)
  - `kubeclusteradm` cluster-admin user cert (`kubeadm.crt`)
  - controller-manager client (static-subject profile `kubeControllerManager`)
  - scheduler client (static-subject profile `kubeScheduler`)

### D2: CA #2 bootstrap mirrors CA #1 (shell, no new profiles, no DNS)

CA #2 is created on the IPA server (delegated from the master's `ipa-certs` flow) by mirroring
`ipa-kubernetes-ca.yml`. It uses the same **shell** `ipa` commands as CA #1 (the installed
`freeipa.ansible_freeipa` v1.17.0 collection does not ship `ipa_ca`/`ipa_ca_acl` modules, so the
existing CA #1 bootstrap already uses shell `ipa ca-add`/`ipa caacl-*`; CA #2 mirrors that):

- `ipa ca-add kubeclusteradm --subject "CN=kubeclusteradm,O=<domain upper>"` — creates CA #2
  (subject mirrors CA #1's `CN=kubernetes-ca` with the `kubeclusteradm` CN).
- `ipa caacl-add kubeclusteradm-acl --usercat=all` — creates CA #2's CA ACL (mirrors CA #1's
  `kubernetes-ca-acl`, which is `usercat=all`).
- `ipa caacl-add-ca kubeclusteradm-acl --ca kubeclusteradm` — links CA #2 to its ACL.
- `ipa caacl-add-profile kubeclusteradm-acl --certprofile kubeAdministrators` and
  `ipa caacl-add-profile kubeclusteradm-acl --certprofile kubernetesNodes` — link the two
  **global** profiles to CA #2's ACL. FreeIPA cert profiles are global objects; linking them to
  CA #2 lets CA #2 sign the same subject shapes as CA #1.

No new profile names are needed (profiles are global; CA #1 keeps `kubeAdministrators` and
`kubernetesNodes`, CA #2 is linked to both). No DNS A+PTR for CA #2: CA #2's self-signed CA cert
carries only a subject (`CN=kubeclusteradm,O=...`) with **no IP SANs**, so the IP-SAN-reachability
DNS work CA #1 performs (A+PTR for the apiserver IP SANs) is not needed for CA #2.

**Host grants**: `usercat=all` does not cover host principals, and the unattended renewal path
re-issues CA #2 client certs *as* host principals (front-proxy as `host/<master>`, node-client
as `host/<node>`), so the CA #2 ACL also gets explicit host grants for every cluster host
(master, nodes, and the IPA server) in `tasks/ipa-cert-renewal.yml` (master-only, delegated to
idm) — mirroring the CA #1 grant loop.

### D3: Cert requests switch `ca` from `kubernetes-ca` to `kubeclusteradm`

| Cert | Before (ca / profile) | After (ca / profile) |
|------|----------------------|---------------------|
| apiserver serving | `kubernetes-ca` / `kubeAdministrators` | unchanged (CA #1) |
| front-proxy client | `kubernetes-ca` / `kubeAdministrators` | `kubeclusteradm` / `kubeAdministrators` (CA #2) |
| kubelet client | `kubernetes-ca` / `kubeAdministrators` | `kubeclusteradm` / `kubeAdministrators` (CA #2) |
| node client | `kubernetes-ca` / `kubernetesNodes` | `kubeclusteradm` / `kubernetesNodes` (CA #2) |
| kubeclusteradm admin | `kubernetes-ca` / `kubeAdministrators` | `kubeclusteradm` / `kubeAdministrators` (CA #2) |

The `profile_id` values are unchanged (the profiles are global); only the `ca` parameter moves to
`kubeclusteradm`.

The **controller-manager** and **scheduler** client certs are **re-issued from CA #2** via
**static-subject certificate profiles** (see D3a). The original design assumed they were
CA #1-signed and would stay valid via CA #1 in the bundle — an implementation investigation
(corrected in D3a) found they are signed by the **kubeadm CA (CA #0)**, which the new two-CA
bundle no longer includes, so they are untrusted and the control plane breaks.

### D3a: Static-subject profiles reproduce the exact `system:masters` subjects

The exact subjects `CN=system:kube-controller-manager, O=system:masters` and
`CN=system:kube-scheduler, O=system:masters` are reproduced with two new **global** certificate
profiles created on the IPA server (verified live on the target FreeIPA 4.13.4):

- `kubeControllerManager` — subject `CN=system:kube-controller-manager, O=system:masters`
- `kubeScheduler` — subject `CN=system:kube-scheduler, O=system:masters`

A certificate profile rewrites the issued certificate's subject (the same mechanism the existing
`kubernetesNodes` profile uses for `O=system:nodes`), so the `ipacert` module's `principal`
limitation is not a blocker: the CSR's CN only needs to pass the host-principal check (the CSR is
generated with the master's hostname and the request uses `principal` `host/<master>`); the
profile decides the issued subject. Both profiles are created next to the existing global
profiles in `ipa-kubernetes-ca.yml` and linked to the CA #2 ACL in `ipa-kubeclusteradm-ca.yml`.

The re-issue runs in `tasks/kube-system-client-certs.yml` (included from `ipa-certs.yml` after
`kube-apiserver-kubelet-client.yml`, once the API runs the new serving cert + client bundle):
per component it generates a key + clientAuth CSR, requests the cert from CA #2 with the
static-subject profile, installs key/cert under `/etc/kubernetes/pki/`, re-embeds them into
`controller-manager.conf` / `scheduler.conf` (base64-embedded `client-certificate-data` /
`client-key-data` via `kubectl config set-credentials` — the scheduler static pod mounts only
its conf, not the pki directory, so file references would break it), and restarts the two
static pods (manifest move pattern, mirroring the renewal script).

### D4: Client CA bundle = CA #2 + CA #1

`ca-bundle.crt` becomes the concatenation of the `kubeclusteradm` (CA #2) CA cert and the
`kubernetes-ca` (CA #1) CA cert, replacing the previous kubeadm + `kubernetes-ca` composition.
A new task downloads CA #2's CA cert to the master (mirroring the existing `ca.crt.new` download
for CA #1).

- `--client-ca-file` (API server + controller-manager) = `ca-bundle.crt` (unchanged reference; new content).
- `--root-ca-file` (scheduler + controller-manager) = `ca-bundle.crt` (unchanged reference; new content).
- **Old-cert window gate** (discovered during implementation): the `ipa-certs.yml` API-restart
  gate validates `healthz` *before* the serving cert is swapped to the IPA-signed one, so on
  a fresh cluster the API still presents the **kubeadm-signed** serving cert. The old
  bundle (kubeadm + CA #1) covered that window; the new bundle does not contain the kubeadm
  CA. The gate therefore anchors to a temporary file holding all three CAs the API may
  present at that point: `ca.crt.kubeadm` + `ca-bundle.crt` (CA #2 + CA #1), built from the
  already-slurped CA certs (kubeadm CA slurped fresh; CA #2/CA #1 reuses the bundle
  registrations).
- `ca.crt` = CA #1 only (unchanged) — the trust anchor for verifying the serving cert.
- Kubeconfig `certificate-authority` = `ca.crt` (CA #1, unchanged) — verifies the CA #1-signed serving cert.
- `--cluster-signing-cert-file` (controller-manager) = `ca.crt.kubeadm` (unchanged; retained kubeadm CA for CSR-based signing).
- **Gate auth ordering** (discovered during implementation): the `ipa-pki-swap` verification
  tasks (KCM-lease gate via `k8s_info`, Ready gate via `kubectl`) and the `kubectl get nodes`
  verification of the `kubeclusteradm` admin credential all authenticate with
  `admin.conf`, whose client cert must be CA #2-issued to be trusted by the new bundle.
  `main.yml` therefore runs `ipa-kube-admin-credential.yml` (admin user + `kinit`) →
  `admin-user.yml` (CA #2 cert re-issue, `admin.conf` re-embed, `kubectl get nodes`
  verification) **before** `ipa-pki-swap.yml` (gates). The `kubectl get nodes` verification
  moved from `ipa-kube-admin-credential.yml` to the end of `admin-user.yml` so it runs after
  the `admin.conf` re-embed.

The bundle includes CA #1 so the cluster can verify the serving cert (signed by CA #1), and
includes CA #2 so it can verify all client certs (signed by CA #2). The kubeadm CA is no longer in
the client bundle (retained only as `--cluster-signing-cert-file`).

### D5: File layout on the master (one new file: CA #2's CA cert)

| File | Content | Used by |
|------|---------|---------|
| `ca.crt` | CA #1 (`kubernetes-ca`) | `certificate-authority` in kubeconfigs; verifies serving cert |
| `ca.crt.kubeadm` | retained kubeadm CA | `--cluster-signing-cert-file` (controller-manager) |
| `ca.crt.kubeclusteradm` (new) | CA #2 (`kubeclusteradm`) | `ca-bundle` input |
| `ca-bundle.crt` | CA #2 + CA #1 | `--client-ca-file`, `--root-ca-file` |

Client-auth verification path: the API server verifies each client cert against `--client-ca-file`
(`ca-bundle.crt` = CA #2 + CA #1), so both CA #2-signed client certs and (during a transition
window) CA #1-signed certs remain valid.

### D6: Master kubelet client cert is wired into kubelet.conf (found during integration verification)

The full-cycle run left the master node `NotReady` after the swap: the master's kubelet log
showed `Unable to register node with API server: Unauthorized` on every API call.
`/etc/kubernetes/kubelet.conf` still pointed `client-certificate`/`client-key` at the
kubeadm-CA-signed `/var/lib/kubelet/pki/kubelet-client-current.pem`, which the two-CA client
bundle no longer trusts. The CA #2-signed `apiserver-kubelet-client.{crt,key}` existed on disk
but was never wired in (node kubelets are unaffected: `kube-install-join-node.yml` generates
their kubeconfig directly with `client-certificate: /etc/kubernetes/pki/node-client.crt`).

- `tasks/kube-apiserver-kubelet-client.yml` re-points `kubelet.conf` at the CA #2-signed
  cert/key (two idempotent `replace` tasks).
- `tasks/ipa-pki-swap.yml` restarts the master kubelet after the swap (the running kubelet pins
  its client cert and trust anchor in memory at boot; a `notify` is too late — handlers flush at
  end of play, after the `calico-ca-recovery` gate) and gates on the master node reporting Ready
  before the Calico data-plane recovery: a calico-node pod on a `NotReady` node can never be
  Ready, so the DaemonSet rollout gate would time out on the master. The restart is gated on the
  `apiServerOverride` block change so a re-converge does not churn the kubelet.

### D7: Master kubelet unit must not bootstrap a client cert (found during 9.3 verification)

With the client cert wired (D6), the full-cycle re-run still left the master node `NotReady`
after the swap: the master's kubelet unit still inherited `--bootstrap-kubeconfig` from the
package drop-in `/usr/lib/systemd/system/kubelet.service.d/10-kubeadm.conf`. With
`rotateCertificates: true` (the `config.yaml` default), the kubelet bootstraps a client cert
that the controller-manager `bootstrapsigner` controller auto-approves, signed by the original
kubeadm CA — which the post-swap client CA bundle (`ca-bundle.crt` = CA #2 + CA #1) does not
contain. The kubelet then switches to that store cert and is `Unauthorized` on every API call.

- `tasks/kube-apiserver-kubelet-client.yml` removes the `10-kubeadm.conf` drop-in and writes a
  clean `20-orchestration.conf` (kubelet.conf (IPA cert) only, no bootstrap, no rotation,
  `--node-ip` pinned to the master IP written by `kubeadm init`), mirroring the node drop-in.
- It disables `rotateCertificates` in `config.yaml` (`replace`, idempotent) and removes the
  `/var/lib/kubelet/pki` store and the orphaned `bootstrap-kubelet.conf`.
- The kubelet restart is gated on the unit/credential tasks reporting a change, so a
  re-converge with no changes does not churn the kubelet.

## Risks / Trade-offs

- **Re-converge / existing cluster**: switching the client cert issuer from CA #1 to CA #2
  requires re-issuing the client certs and rebuilding the bundle. Because the bundle includes both
  CAs, in-flight certs signed by either CA remain valid during the transition window.
- **Name overlap**: `kubeclusteradm` is both a FreeIPA CA name and the cluster-admin user name.
  They are distinct FreeIPA objects (CA vs. user) sharing the same CN. The CA is referenced via
  `ipa_kubeclusteradm_ca_name` and the user via `kubeclusteradm_user`; no collision in the tasks.
- **Module availability**: CA #2 bootstrap uses the same **shell** `ipa` commands as the existing
  CA #1 bootstrap (the installed collection v1.17.0 does not ship `ipa_ca`/`ipa_ca_acl` modules),
  so it introduces no new module dependencies and keeps the two CAs symmetric.
- **Ordering**: CA #2 must exist before any client cert is requested from it. `ipa-certs.yml`
  includes `ipa-kubeclusteradm-ca.yml` immediately after `ipa-kubernetes-ca.yml`, so CA #2 exists
  before `ipa-front-proxy.yml` / `kube-apiserver-kubelet-client.yml` (in the same include) and
  before `kube-install-join-node.yml` / `admin-user.yml` (later includes in `main.yml`).
- **Control-plane restart window**: the KCM/scheduler client re-issue restarts both static pods
  (`kube-system-client-certs.yml`), so the controller-manager and scheduler are briefly down
  mid-converge. No data is lost (leader leases are re-acquired on restart) and the cluster is
  not yet joined to at that point (node join runs after `ipa-certs`); the `ipa-pki-swap` gates
  then confirm the KCM lease is fresh and the scheduler is Ready before proceeding.

## Follow-ups (found during integration verification)

- **ipaservice resolvability race (tasks 8.1–8.2)**: the SAN-alias `ipaservice` task in
  `ipa-api-server.yml` failed intermittently with "Host ... does not have corresponding DNS
  A/AAAA record". The `ipaservice` pre_callback runs `util.verify_host_resolvable()`, which
  resolves through the IPA *server host's system resolver* (not the zone database); the idm
  link's `resolvectl` races the authoritative IPA DNS against the public upstream
  (NXDOMAIN), with the result cached per negative-cache TTL — flaky per cache window even
  though the A records exist in the zone (created by `ipa-kubernetes-ca.yml` earlier).
  Fix: `force: True` on the SAN-alias task (skips only the resolvability check; the
  zone-record invariant is enforced by `ipa-kubernetes-ca.yml`), matching the sibling
  `HTTP/<master>` tasks that already use `force: True`.
