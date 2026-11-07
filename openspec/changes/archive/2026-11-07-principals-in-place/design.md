# Design: principals-in-place

## Context

See `proposal.md` — Why. The current state, verified against the code:

- **Runtime exemplar.** `templates/kube-cert-renew.sh.j2` already implements the target model: every host `kinit -kt`s with its **own** keytab (`/etc/krb5.keytab` host principal; the master additionally uses the `kubeclusteradm` user keytab) and self-enrolls its own certificates — node client cert from CA #2 (`kubeclusteradm`, `kubernetesNodes` profile, principal `host/<node>`, CSR subject `O=system:nodes/CN=<host>`), front-proxy/KCM/scheduler from CA #2 with principal `host/<master>`, apiserver from CA #1. Provisioning should converge toward this, not vice versa.
- **Provisioning today violates the model.** `tasks/kube-node-cert.yml` generates the node's private key + CSR on the **master** (`/tmp/node-<host>.key/.csr`), shuttles them master → control node → idm, and enrolls with an **admin** ticket minted on idm. `tasks/kube-install-join-node.yml` gates similarly on admin tickets on idm. `tasks/ipa-api-server.yml`, `ipa-front-proxy.yml`, `kube-apiserver-kubelet-client.yml`, `ipa-controller-manager-client.yml` run `ipacert`/`ipa*` modules **un-delegated on the master with `ipaadmin_password`**. All scratch caches are `/tmp/.*.ccache` dotfiles named after the calling task file. The renewal timer runs with no `KRB5CCNAME`, so `kinit` lands in the ambient `/tmp/krb5cc_0`; the `kubeclusteradm` keytab sits at `/tmp/kubeclusteradm.keytab` on idm and is base64-shuttled to the master.
- **Ordering blocker.** CA-ACL host grants (`kubernetes-ca-acl`, `kubeclusteradm-acl`) run in `tasks/ipa-cert-renewal.yml` — a master-play step **after** node join — while `usercat=all` covers users only, not hosts (`tasks/ipa-ca-acl-host.yml` documents this). Self-enrollment pre-join is impossible until the grants move earlier.
- **Constraints that shape the design:**
  - `ipa caacl-add-host` / `caacl-add-profile` exit rc=1 "This entry is already a member" → keep the existing check-then-add pattern (`tasks/ipa-ca-acl-host.yml`).
  - `community.general.ipa_getkeytab` cannot do a non-rotating export (`krbPrincipalKey` behind a search-only ACI) → the `kadmin.local ktadd -norandkey` shell exception stays, and it only runs on the IPA master.
  - `krb_ticket`'s idempotence `klist` runs without `-c`, so scratch caches must keep being pre-cleared (`file: state: absent`) before acquisition.
  - `tasks/prereq.yml` installs `python3-cryptography` on **all** hosts, so nodes can run `community.crypto` locally; nodes are IPA clients (enrolled, with `/etc/krb5.keytab`) before join.
  - The `kubeclusteradm` user/keytab does not exist until late converge — that justifies an admin identity only for `kubeclusteradm`'s own credential, never for a node's host-identity enrollment.

## Goals / Non-Goals

**Goals:**
- Each certificate negotiated by the host that will use it, authenticated with that host's own host keytab (or `kubeclusteradm` keytab for the admin cert); private keys never leave their host.
- CA-ACL host grants applied on idm inside the CA chain, before any self-enrollment.
- One scratch-cache convention: `/run/krb5cc/<principal>.<purpose>.ccache`, tmpfs, root-only, pre-cleared.
- Timer runtime isolated in a unit-scoped cache + keytab under `/var/lib/kube-cert-renew` (0600), ambient `/tmp/krb5cc_0` unused.
- Realm admin password confined to control node + idm.

**Non-Goals:**
- No change to certificate subjects, CAs, profiles, the two-CA trust model, or the renewal schedule.
- No change to the `kadmin.local ktadd -norandkey` / `cpw` mechanisms or their spec history.
- No relocation of the master's `kube_credential_folder` (`kubeadm.pem/crt`, `admin.conf` re-embedding depend on it).
- Not touching unrelated `freeipa.ansible_freeipa` user/host-management calls that already run delegated on idm with the managed password.

## Decisions

**D1 — Scratch-cache convention: `/run/krb5cc/<principal>.<purpose>.ccache`.**
`/run` is tmpfs (nothing persists across boots), directory mode `0700` root-owned, created once in `tasks/requirements.yml` (`file: state: directory`). Names encode identity, e.g. `admin.ipa_k8s_ca.ccache`, `host-node1.node_cert.ccache`, `kubeclusteradm.admin_cred.ccache`. Rejected: keeping `/tmp` dotfiles (world-writable dir; names encode the calling file, not the principal — the R4 failure this fixes).

**D2 — Provisioning converges toward the runtime script (node-local enrollment).**
Rewrite `tasks/kube-node-cert.yml` so the node runs, on itself: `community.crypto.privatekey` → `community.crypto.x509_certificate` (CSR, `O=system:nodes`, CN=hostname) → `community.general.krb_ticket` (`keytab: /etc/krb5.keytab`, principal `host/<node>`, cache per D1) → `freeipa.ansible_freeipa.ipacert` (`ca=kubeclusteradm`, `profile=kubernetesNodes`, `principal=host/<node>`, `csr_file`/`certificate_out` resolving **on the node**, `env: KRB5CCNAME`). The master-side key/CSR generation, staging, and cleanup tasks are deleted. Rejected: moving only the ticket minting while the master keeps generating keys (private key still shuttles — R2 unhealed; admin-on-idm still load-bearing).

**D3 — CA-ACL host grants move into the CA chain, pre-join; steady-state re-assert stays.**
New include `tasks/ipa-ca-acl-prejoin.yml`: delegated to idm, admin scratch ticket per D1, runs at the end of the CA provisioning chain (`tasks/ipa-certs.yml` flow, after both CAs + profiles exist) and therefore before the node-join play in `tasks/main.yml`. It grants every `ipaclients`/kube host to `kubernetes-ca-acl` and `kubeclusteradm-acl` via the existing check-then-add `tasks/ipa-ca-acl-host.yml` loop. `tasks/ipa-cert-renewal.yml` keeps its grant loop as an idempotent steady-state repair path. Rejected: gating node join on grant existence (on a fresh converge the grants would never arrive before the gate — the master play runs too late, so the gate would wedge converge); rejected: relying on `usercat=all` (never covered hosts — that is the bug the admin ticket masked).

**D4 — Master component certs use the master's own host ticket, mirroring the renewal script.**
`tasks/ipa-front-proxy.yml`, `ipa-controller-manager-client.yml`, `ipa-scheduler-client.yml`, `kube-apiserver-kubelet-client.yml`, `ipa-api-server.yml`: replace un-delegated `ipaadmin_password` module calls with a host-keytab `krb_ticket` on the master (principal `host/<master>`) + `ipacert` authenticated by that ticket, exactly as `kube-cert-renew.sh.j2` already does per cert. The `kubeclusteradm` admin cert keeps keytab-first + admin-password fallback (that principal cannot self-authorize, and it does not exist early).

**D5 — Keytab and timer placement.**
idm export destination: `/var/lib/kube-cert-renew/kubeclusteradm.keytab` (dir 0700 root, file 0600); `kadmin.local ktadd -norandkey` writes it directly (no `/tmp` intermediate), then `slurp` + `copy: content:` delivers it to the master's `kube_credential_folder` (mode 0600) — replacing the `base64 -w0` shuttle. `templates/kube-cert-renew.service.j2` gains `StateDirectory=kube-cert-renew` and `Environment=KRB5CCNAME=FILE:/var/lib/kube-cert-renew/ccache`; the script pre-clears that cache before `kinit`. Rejected: also moving the master's credential folder (ripple through `admin-user.yml` / conf re-embedding for no security gain — folder is already root-owned persistent state).

**D6 — Realm-password confinement via delegation, not new auth.**
Remaining legitimate admin-identity tasks (e.g. `ipauser` key-setting flow in `ipa-kube-admin-credential.yml`, early `kubeclusteradm` enrollment) run `delegate_to: idm` with an admin scratch ticket per D1 — the convention already used by `tasks/ipa-kubernetes-ca.yml`. Rejected: passing `ipaadmin_password` to kube hosts (status quo — the realm password has no business on a worker); rejected: converting shell `ipa` CLI tasks that already authenticate fine (out of scope).

**D7 — Delete the sacrificial host-keytab probe in `tasks/ipa-certs.yml`.**
The probe registers `kca_keytab_usable` with no downstream consumer; the real probes live in `ipa-kube-admin-credential.yml` / `ipa-cert-renewal.yml`. Deletion (monorepo no-dead-code rule) over wiring it to a consumer that doesn't need it.

## Risks / Trade-offs

- [`ipacert` module run on a node instead of delegated to idm may hit client-side auth/packaging gaps] → First implementation task is a one-host spike on a live molecule node; if the module cannot run node-side, fall back to a documented shell exception (`ipa cert-request` on the node with `KRB5CCNAME`) — the invariant (ticket + CSR + key on the owner) holds either way.
- [Fresh converge: self-enrollment hits a missing ACL grant] → Grants are applied in the CA chain before any node play; the from-destroy converge scenario in `tasks.md` is the gate; the steady-state re-assert covers drift.
- [More ticketing tasks → longer converge] → Each `krb_ticket` is a local keytab operation (no network round-trip beyond one KDC AS-REQ); negligible against IPA install time.
- [Pre-existing spec/code drift: main `kerberos-ticketing` spec still describes the keytab export as native `ipa_getkeytab`, while code uses the `kadmin.local` shell exception] → Untouched by this change (D3-history predates it); recorded as an open question, not silently rewritten.
- [Keytab path change leaves a stale `/tmp/kubeclusteradm.keytab` on previously converged VMs] → One cleanup `file: state: absent` task in `ipa-cert-renewal.yml`; molecule VMs are disposable for verification.

## Migration Plan

1. Implement on the current branch; run the full host-OS scenario cycle: `destroy → converge-monorepo → verify-monorepo`, then re-converge for idempotence (per monorepo rules).
2. Rollback: `git revert` + destroy/re-converge. All moved artifacts (`/run/krb5cc`, `/var/lib/kube-cert-renew`) are ephemeral or regenerated by converge; no external state to unwind.

## Open Questions

- Can `freeipa.ansible_freeipa.ipacert` run from a node without `delegate_to` (D2 spike decides module-vs-shell at the node boundary; both satisfy the spec)?
- Whether to later unify the master-side credential folder with `/var/lib/kube-cert-renew` (explicitly deferred, Non-Goal).
