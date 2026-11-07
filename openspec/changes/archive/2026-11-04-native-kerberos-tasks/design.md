# Design: native-kerberos-tasks

## Context

Shell `kinit` in this role is not just a convenience — it is load-bearing state. Six task files mint tickets into the **ambient** per-user cache (`~/.k5.<user>`, `become: true` → `~/.k5.root`) and the downstream `ipa` CLI calls consume whatever happens to be there:

```
                ambient cache ~/.k5.root (per host, per user)
                ┌─────────────────────────────────────────────────┐
                │                                                 │
 master         │  S1 safeguard kinit -kt /etc/krb5.keytab        │
                │  S2 kinit admin (B ca-show ×2)                  │
                │                                                 │
 idm            │  S3 kinit admin (C bootstrap — feeds the whole  │
                │       CA chain: ca-ensure/profile/link-profile) │
                │  S4 kinit admin (join: profile gate + CA fetch) │
                │  S5 kinit -kt / kinit admin (D probes)          │
                │  S6 kinit admin ×2 (E caacl bootstrap + loop)   │
                │  S7 kinit -kt / kinit admin + ipa-getkeytab (E) │
                │  S8 kinit admin (delete: CA + ACL checks)       │
                └─────────────────────────────────────────────────┘
```

Fragilities: (1) a stale/expired ambient ticket is silently reused (`kinit` skips when a cache exists); (2) seven flows on idm share one cache — cross-flow pollution; (3) the rotation flow's persistent keytab append can be shadowed by a stale same-principal entry (the `rm -f` shell task is the only guard). The main spec (`ipa-pki-infra`) carries a loose ticket requirement ("obtained via keytab before cert operations") — it is silent on cache handling, which this change pins down in the new `kerberos-ticketing` capability.

## Conversion map (10 sites, 2 hosts)

| # | File | Runs on | Current | Native conversion | Scratch cache |
|---|------|---------|---------|-------------------|---------------|
| S1 | `ipa-certs.yml` (safeguard, loop host) | master | `command: kinit -kt /etc/krb5.keytab` | pre-clear + `krb_ticket: keytab: true, keytab_path: /etc/krb5.keytab` | `/tmp/.ipa_certs_host.ccache` |
| S2 | `ipa-certs.yml` (B, `ca-show` ×2) | master | `shell: kinit admin; ipa ca-show …` | pre-clear + `krb_ticket: principal: admin, password: …`; `env` on the 2 shell tasks; drop `kinit` line | `/tmp/.ipa_certs_admin.ccache` |
| S3 | `ipa-kubernetes-ca.yml` (C bootstrap) | idm | `shell: kinit admin` | pre-clear + `krb_ticket: principal: admin, password: …`; `env` on the idm-delegated `ipa` consumers in the chain (`ipa-ca-ensure.yml` ×5, `ipa-ca-profile.yml`, `ipa-ca-link-profile.yml`) | `/tmp/.ipa_k8s_ca_admin.ccache` |
| S4 | `kube-install-join-node.yml` (profile gate + CA fetch) | idm | `shell: kinit admin; ipa certprofile-find / ipa ca-show` | pre-clear + `krb_ticket: principal: admin, password: …`; `env` on the 2 shell tasks; drop `kinit` lines | `/tmp/.join_node_admin.ccache` |
| S5 | `ipa-kube-admin-credential.yml` (D probes + verify) | idm | `shell: kinit -kt (probe); kinit admin (password probe)` | 2 block/rescue probes → `kca_keytab_usable` / `kca_password_usable` (the keytab probe carries `principal: "{{ ipa_kube_admin_principal }}"` — keytab-only kinit requests the default host principal, not the keytab's entry; verified 2026-10-30); cpw task: drop `kinit` line (no consumer); verify task: scratch + `env` + `changed_when: false` | `/tmp/.kca_keytab_probe.ccache`, `/tmp/.kca_password_probe.ccache`, `/tmp/.kca_admin.ccache` |
| S6 | `ipa-cert-renewal.yml` (E caacl bootstrap + loop) | idm | `shell: kinit admin` (bootstrap + per-iteration) | pre-clear + **one** `krb_ticket` before the loop; `env` on the looped caacl shell task; drop both `kinit` lines | `/tmp/.renewal_admin.ccache` |
| S7 | `ipa-cert-renewal.yml` (E rotation) | idm | `shell: kinit -kt (probe); kinit admin` + `command: ipa-getkeytab` + `rm -f` inside one shell | block/rescue keytab probe → `kca_rotation_keytab_usable` (carries `principal: "{{ ipa_kube_admin_principal }}"` — see S5 note); rotation block = declarative `file: state: absent` + **`kadmin.local ktadd -norandkey`** shell exception (the native `ipa_getkeytab --retrieve` mode is refused by FreeIPA 4.13 — see D3 amendment); delete the `kinit admin` bootstrap and `rm -f` line | `/tmp/.kca_rotation_probe.ccache` (probe); the export needs no ticket (kadmin.local binds to the local KDB) |
| S8 | `delete-ipa-cleanup.yml` (CA + ACL checks) | idm | `shell: kinit admin; ipa ca-find` (ACL check reuses the ticket) | pre-clear + `krb_ticket: principal: admin, password: …`; `env` on both check tasks; drop `kinit` line | `/tmp/.cleanup_admin.ccache` |
| S9 | `kube-node-cert.yml` (CA #2 node client cert) | master→idm | `ipacert: ipaadmin_password: …` (module `temp_kinit` on master) | pre-clear + `krb_ticket: principal: admin, password: …` on idm; `ipacert` delegated to idm with `environment: KRB5CCNAME`, **no password param**; CSR/cert shuttled via `slurp`/`copy: content:`; staged temp files cleaned (D9) | `/tmp/.node_cert_admin.ccache` |
| S10 | `admin-user.yml` (CA #2 admin client cert) | master→idm | `ipacert: ipaadmin_password: …` (module `temp_kinit` on master) | pre-clear + block/rescue `krb_ticket` on idm (keytab `kubeclusteradm` first, admin-password rescue); `ipacert` delegated to idm with `environment: KRB5CCNAME`, **no password param**; CSR/cert shuttled; temp files cleaned (D9) | `/tmp/.admin_user_admin.ccache` |

## Decisions

**D1 — One scratch cache per purpose, pre-cleared, passed via `env`.**
Every ticketing task acquires into a static per-purpose path under `/tmp`, preceded by a `file: state=absent` pre-clear. Consumers (including delegated ones — `env` applies on the delegation target) get `env: KRB5CCNAME: <path>`.
- *Why static names*: debuggable (`krb5cc_…` inspection), identical across re-runs, no `/tmp` litter.
- *Why pre-clear*: the pre-existing stale/expired cache is the whole bug; pre-clearing makes "fresh" a property of the task, not of host history.
- *Pre-clear also defeats the module's short-circuit*: `krb_ticket`'s `check_ticket_present` runs `klist -l` **with no `-c` flag** (the module's klist runner exposes no cache-name format), so it inspects the ambient cache and string-matches `cache_name` against the output — and `klist` lists *expired* tickets as present. With `env: KRB5CCNAME` on the task, a stale scratch cache would make the module skip `kinit` and silently reuse an expired ticket; the pre-clear is what makes freshness structural, not a property of a check that cannot see the scratch cache on its own.
- *Rejected*: ambient (status quo — pollution + staleness); unique-per-run names — orphaned caches accumulate, not debuggable.

**D2 — Keytab usability probe = block/rescue `krb_ticket: keytab: true` into a scratch cache.**

```yaml
block:
  - ansible.builtin.file:
      path: /tmp/.<purpose>_probe.ccache
      state: absent
  - community.general.krb_ticket:
      keytab: true
      keytab_path: <keytab>
      cache_name: /tmp/.<purpose>_probe.ccache
      become: true
rescue:
  - ansible.builtin.set_fact:
      <purpose>_usable: false
```

Usable keytab mints a fresh ticket (block completes → default `usable: true`); a rotated key fails at the KDC → rescue. No ambient read, no ambient write, no change reporting (the cache is ephemeral — same as today's `changed_when: false`).
- *Rejected*: `failed_when: false` + `register.<r>.is succeeded` — a task that fails its check fails the playbook **before** `failed_when` is evaluated; the block/rescue pattern is the idiom this role already uses (the D verify task).

**D3 — Export mechanism: `kadmin.local ktadd -norandkey` shell exception (native module amended out — see below).**

```yaml
- name: "… remove unusable keytab before re-export"        # delete step, declarative
  ansible.builtin.file: { path: /tmp/kubeclusteradm.keytab, state: absent }
  delegate_to: "{{ groups[idm_group] | first }}"
  become: true
  when: … and not (kca_rotation_keytab_usable | default(true))

- name: "… export kubeclusteradm keytab (non-rotating)"
  ansible.builtin.command: >-
    kadmin.local -q
    "ktadd -norandkey -k /tmp/kubeclusteradm.keytab kubeclusteradm@{{ company_domain | upper }}"
  delegate_to: "{{ groups[idm_group] | first }}"
  become: true
  when: … and not (kca_rotation_keytab_usable | default(true))
```

- The gate is the usability probe: in steady state both tasks are skipped (no churn); when they run they genuinely regenerate → truthful change reporting, no blanket `changed_when`.
- Delete-then-export makes append-shadowing structurally impossible (ktadd appends; the file must hold exactly the current key) — the spec invariant becomes structural, not a shell chore.
- `kadmin.local` binds to the **local KDB** on the IPA master: no ticket, no keytab, no password in task parameters; `-norandkey` writes the stored key verbatim (no rotation, kvno unchanged — verified 2026-11-01: keytab authenticates AND the managed password still mints a ticket after export).

*Amendment (2026-11-01, fresh-VM converge)*: the original D3 selected **native `community.general.ipa_getkeytab`** with `sasl_mech: GSSAPI` (ticket mode via `environment: KRB5CCNAME` → S6's scratch admin cache) + `retrieve_mode: true` + `force: true`, believed VM-verified (2026-10-28). The first fresh-VM converge falsified that: the module ran with a valid admin ticket (klist confirmed `admin@OSGILIATH.TEST` + `ldap/idm` service ticket) and the server rejected `--retrieve` with **"Insufficient access rights"** — reproduced manually for the user principal (`kubeclusteradm`), a host principal and a service principal. Root cause: FreeIPA (4.13.4 here) protects `krbPrincipalKey` behind a search-only ACI (`acl "Search existence of password and kerberos keys"; allow(search) userdn="ldap:///all"`), and the `curkeys` retrieve variant requires the requester to READ that attribute — which no requester, admin included, may by default. The module's only other mode generates a new key (rotates), which the D8 credential contract forbids. **No native equivalent exists for a non-rotating export → the monorepo shell-exception rule applies**, with the reason stated in the task comment. The export's `environment:`/`sasl_mech`/ticket dependency is gone; S6's scratch admin ticket remains solely for the looped `ipa caacl` consumers.

*Rejected*: bind mode (`bind_dn`/`bind_pw`) — the admin DN is not derivable from `company_domain` (FreeIPA `cn=users` nesting; derived-DN attempts failed with LDAP 49, 4/4); binding as `cn=Directory Manager` would put the DM password in `ipa-getkeytab`'s **argv** (ps-visible) for an operation `kadmin.local` performs locally without any secret.

*Rejected*: keep `ipa-getkeytab` in shell (default ktadd mode) with an env'd scratch ticket — it rotates the key on every re-export (forbidden by D8).

*Rejected*: hand-add an ACI granting admins read of `krbPrincipalKey` to unblock `--retrieve` — it widens Kerberos-key exposure cluster-wide for no benefit over the master-local `kadmin.local` path.

**D4 — Drop the `kinit` line in the `ipa-kube-admin-credential.yml` cpw task.**
`kadmin.local -p` is a local DB operation — no ticket. The cpw task's `kinit admin` has no downstream consumer (verified: the only ticket consumer in the file is the verify task, which gets its own scratch cache). Dead weight today, gone after the change.

**D5 — Ticket tasks report no change.**
`krb_ticket` tasks carry `changed_when: false`: a scratch cache is ephemeral state, in the same class as the monorepo rule's existing `kinit` credential-renewal tolerance ("renews the credential cache only, no persistent state"). Idempotence: pre-clear + re-acquire → no reported change, no churn.

**D6 — Shell `ipa` CLI consumers stay shell, gain `env`.**
The installed `freeipa.ansible_freeipa` ships no CA/CA-ACL/certprofile modules (per the existing task-file comments), so consumer commands stay `command`/`shell` with `env: KRB5CCNAME` attached. The monorepo AGENTS.md `kinit` exception entry stays for the other roles (`tcharl.ansible_nameserver`, `tcharl.ansible_securehost`, `tcharl.nfs_server` — verified: these are the only roles with shell `kinit` sites); this role stops contributing usage sites.

**D7 — Cache location `/tmp`, same exposure class as today.**
The scratch caches hold the same material as today's `~/.k5.root` (host/service tickets, admin ticket). `/tmp` with `become: true` is root-readable — the same class as a root home cache. Optional hardening (0600 on the cache files) is a follow-up, out of scope.

**D8 — Non-rotating export (`ktadd -norandkey`): the key-stability contract.**

`kadmin.local ktadd -norandkey` (verified on a running VM 2026-11-01: export succeeds, kvno unchanged, keytab authenticates, managed password still mints a ticket) replaces both ktadd's default rotate-on-re-export and the refused `--retrieve` mode (D3 amendment). Consequences:

- The managed password is **not** invalidated by re-export → the `Too soon to change password` exposure in `ipa-kube-admin-credential.yml` loses its rotation trigger (its `cpw` gate — both credentials unusable — is unchanged).
- The keytab **tracks the KDB**: if the KDB key changes externally (manual rotation), the next regeneration writes the current key — the usability gate (the keytab probe) remains the sole trigger, unchanged.
- **The main-spec contract is superseded**: the `ipa-kube-admin-credential` steady-state clause ("the export rotates the principal key as a documented side effect — the managed password is dead by design; a non-rotating keytab export does not exist") is factually wrong and is replaced by a MODIFIED requirement delta in this change.

*Upstream corroboration (FreeIPA client source + `ipa-getkeytab(1)` + MIT `kadmin(8)`, investigated 2026-10-28, corrected 2026-11-01)*: `ipa-getkeytab`'s two modes are distinct wire variants of the `GetKeytabControl` extended-operation payload — `newkeys` (server generates a fresh key, i.e. **rotates**; man page: "resets the secret … renders all other keytabs for that principal invalid") vs `curkeys` (`-r`, server returns the stored key). Non-rotation via `curkeys` additionally requires the requester to read `krbPrincipalKey`, which FreeIPA's default ACI set denies to every requester (search-only ACI; VM-verified rejection on 4.13.4) — so over the wire there is no usable non-rotating export. On the master, MIT kadmin reads the KDB directly: `ktadd` rotates unless `-norandkey` is given (kadmin(8): "Do not randomize the string used to derive this principal's key"), and with it the stored key is written verbatim — the protocol-level non-rotation property now lives in the `-norandkey` flag, not in `--retrieve`. Caveat for future readers: the module's `bind_dn` doc caveat ("this will generate a new keytab, invalidating previously retrieved keytabs") correctly warns that the module has no server-side non-rotating path on this build — the reason D3 no longer uses the module at all.

*Rejected*: keep ktadd's default rotation — it preserves current behavior but invalidates the password on every re-export (recoverability loss + a min-password-age window), and the rotation side effect buys nothing for this role's flows (the keytab is regenerated on demand, and consumers use the keytab, not the password).

**D9 — CA #2 client-certificate enrollments (S9/S10) go passwordless by delegating `ipacert` to idm with a scratch ticket (amendment, 2026-11-04, user-reported "switch not accurate as expected").**

The first half-migration draft enrolled CA #2 client certs through `community.general.ipa_getcert` — **a module that does not exist** in the installed `community.general` 14.0.0 (only `ipa_getkeytab`/`krb_ticket` ship there; verified in the installed collection tree). That module-not-found failure was the reported inaccuracy. The correct native path is the already-used `freeipa.ansible_freeipa.ipacert`: its `ipa_connect` → `valid_creds` honors `environment: KRB5CCNAME` for GSSAPI negotiation and only falls back to the password `temp_kinit` when no cache is set, and `ipaadmin_password` is not required by the argspec (verified in the installed `module_utils/ansible_freeipa_module.py`).

Mechanics: `ipacert` runs delegated to **idm** (where the scratch ticket, the `kubeclusteradm` keytab, and the IPA API live — `krb_ticket` tooling is only VM-proven on idm). `csr_file`/`certificate_out` are host-local to the delegated host, so the CSR is shuttled master→idm and the issued cert idm→consumer via in-memory `slurp` + `copy: content:` (no secret material lands in task parameters); staged `/tmp` files are cleaned after.

Identity by ordering position (main.yml graph is load-bearing):
- **S9 node cert** runs before `ipa-kube-admin-credential.yml` → neither the `kubeclusteradm` user nor its keytab exists yet, and only an admin-class identity may enroll a `host/...` principal (see policy verification below) → **admin password ticket**, identical to the S4/S6/S8 convention.
- **S10 admin cert** runs after the keytab export → **kubeclusteradm keytab ticket** (steady state is fully passwordless), block/rescue fallback to the admin password ticket (same idiom as the S5 probes).

*Policy verification on the running VM (2026-11-04, FreeIPA 4.13.4)*, which settled two questions that the CA ACL dump alone could not:
- `kubeclusteradm-acl` has `User category: all`, the four kube profiles, and explicit `Hosts:` grants. A **self**-request (`--principal=kubeclusteradm`, user cert, `kubeAdministrators`) issued fine as the non-admin user — the non-empty host list does not constrain user principals.
- A non-admin request **on behalf of another principal** (`--principal=host/node1…`, even though that host is in the ACL) failed with `Insufficient access: not allowed to perform operation: request certificate` — requesting for foreign principals requires admin/CA-agent rights regardless of CA ACL. Hence S9's admin ticket is a FreeIPA policy necessity, not a shortcut; it matches the pre-change behavior (the password used was always the admin's).

## Stale-comment finding (S1)

The S1 safeguard comment says the shell `ipa` calls in the CA chain "run as root without a ticket" on the loop host (master) — but every shell `ipa` task in the chain (`ipa-ca-ensure.yml`, `ipa-ca-profile.yml`, `ipa-ca-link-profile.yml`) is **delegated to idm** and consumes idm's ticket (S3). No master-side ticket consumer exists. S1 is retained as a safeguard (converted to scratch) and its comment is corrected to match reality. *Follow-up (out of scope)*: consider deleting S1 entirely once convergence confirms nothing master-side needs a ticket.

## Risks

- **`krb_ticket` keytab+cache composition — verified on the VM (2026-10-30)**: the module runs `kinit [-t <keytab>] [-c <cache>] [principal]`. Keytab-only (no `principal`) mints the machine's **default (host) principal** from the keytab — NOT the keytab's first entry (the design's original assumption was wrong; on idm, keytab-only against `/tmp/kubeclusteradm.keytab` fails with "Keytab contains no suitable keys for host/idm.osgiliath.test@OSGILIATH.TEST"). S1 is safe keytab-only (the host keytab holds the default host principal — verified: rc=0, TGT minted into the scratch cache). **The S5/S7 probes therefore carry `principal: "{{ ipa_kube_admin_principal }}"`** (realm-less; kinit resolves the default realm) — verified: `kinit -k -t /tmp/kubeclusteradm.keytab -c <cache> kubeclusteradm` mints the `kubeclusteradm@OSGILIATH.TEST` TGT (rc=0).
- **Non-rotating export on the stale-keytab path** — verified in the fresh case (kvno unchanged, keytab valid, password alive, 2026-11-01); the stale-keytab path (KDB key rotated out, regeneration triggered) is exercised by task 5.6: re-export must write the current key without rotation, without invalidating the managed password.
- **`freeipa-client` on idm** — probes/ticketing on idm need `krb5` + `freeipa-client`; already present (IPA server hosts ship the client; today's shell `kinit` on idm proves it).
- **`env` on delegated tasks** — `env` applies on the delegation target; first converge is the proof (the E loop task is delegated; its `env` must reach idm).
- **`krb5.conf` on idm** — `KRB5CCNAME` must resolve against the same realm config as today's ambient flow (same host, same config — no change).

## Migration

No state migration: scratch caches are fresh by construction (pre-cleared); ambient caches are left in place (untouched — other flows and other roles may still use them). Behavioral equivalence: consumer commands unchanged; only the ticket source moves from ambient to scratch. First converge after the change is the proof; `destroy` re-runs the delete-flow (S8) from scratch on each cycle.

Reboot: systemd-tmpfiles clears idm's `/tmp`, discarding the working keytab; the next converge's probe fails and the non-rotating re-export restores it (D3) with no KDB change and no password invalidation. Under the old rotating export the same reboot-induced re-export would have invalidated the managed password — non-rotation turns a reboot from a credential-breaking event into a no-op refresh.
