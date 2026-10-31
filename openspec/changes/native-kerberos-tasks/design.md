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

Fragilities: (1) a stale/expired ambient ticket is silently reused (`kinit` skips when a cache exists); (2) seven flows on idm share one cache — cross-flow pollution; (3) the rotation flow's persistent keytab append can be shadowed by a stale same-principal entry (the `rm -f` shell task is the only guard). Plus one spec/code mismatch: `ipa-pki-infra`'s scenario promises a "scratch ticket cache" the code never creates.

## Conversion map (8 sites, 2 hosts)

| # | File | Runs on | Current | Native conversion | Scratch cache |
|---|------|---------|---------|-------------------|---------------|
| S1 | `ipa-certs.yml` (safeguard, loop host) | master | `command: kinit -kt /etc/krb5.keytab` | pre-clear + `krb_ticket: keytab: true, keytab_path: /etc/krb5.keytab` | `/tmp/.ipa_certs_host.ccache` |
| S2 | `ipa-certs.yml` (B, `ca-show` ×2) | master | `shell: kinit admin; ipa ca-show …` | pre-clear + `krb_ticket: principal: admin, password: …`; `env` on the 2 shell tasks; drop `kinit` line | `/tmp/.ipa_certs_admin.ccache` |
| S3 | `ipa-kubernetes-ca.yml` (C bootstrap) | idm | `shell: kinit admin` | pre-clear + `krb_ticket: principal: admin, password: …`; `env` on the idm-delegated `ipa` consumers in the chain (`ipa-ca-ensure.yml` ×5, `ipa-ca-profile.yml`, `ipa-ca-link-profile.yml`) | `/tmp/.ipa_k8s_ca_admin.ccache` |
| S4 | `kube-install-join-node.yml` (profile gate + CA fetch) | idm | `shell: kinit admin; ipa certprofile-find / ipa ca-show` | pre-clear + `krb_ticket: principal: admin, password: …`; `env` on the 2 shell tasks; drop `kinit` lines | `/tmp/.join_node_admin.ccache` |
| S5 | `ipa-kube-admin-credential.yml` (D probes + verify) | idm | `shell: kinit -kt (probe); kinit admin (password probe)` | 2 block/rescue probes → `kca_keytab_usable` / `kca_password_usable`; cpw task: drop `kinit` line (no consumer); verify task: scratch + `env` + `changed_when: false` | `/tmp/.kca_keytab_probe.ccache`, `/tmp/.kca_password_probe.ccache`, `/tmp/.kca_admin.ccache` |
| S6 | `ipa-cert-renewal.yml` (E caacl bootstrap + loop) | idm | `shell: kinit admin` (bootstrap + per-iteration) | pre-clear + **one** `krb_ticket` before the loop; `env` on the looped caacl shell task; drop both `kinit` lines | `/tmp/.renewal_admin.ccache` |
| S7 | `ipa-cert-renewal.yml` (E rotation) | idm | `shell: kinit -kt (probe); kinit admin` + `command: ipa-getkeytab` + `command: rm -f` | block/rescue keytab probe → `kca_rotation_keytab_usable`; rotation block = **`community.general.ipa_getkeytab`** (`bind_dn`/`bind_pw`, `force: true`); delete the `kinit admin` bootstrap and `rm -f` tasks | `/tmp/.kca_rotation_probe.ccache` |
| S8 | `delete-ipa-cleanup.yml` (CA + ACL checks) | idm | `shell: kinit admin; ipa ca-find` (ACL check reuses the ticket) | pre-clear + `krb_ticket: principal: admin, password: …`; `env` on both check tasks; drop `kinit` line | `/tmp/.cleanup_admin.ccache` |

## Decisions

**D1 — One scratch cache per purpose, pre-cleared, passed via `env`.**
Every ticketing task acquires into a static per-purpose path under `/tmp`, preceded by a `file: state=absent` pre-clear. Consumers (including delegated ones — `env` applies on the delegation target) get `env: KRB5CCNAME: <path>`.
- *Why static names*: debuggable (`krb5cc_…` inspection), identical across re-runs, no `/tmp` litter.
- *Why pre-clear*: the pre-existing stale/expired cache is the whole bug; pre-clearing makes "fresh" a property of the task, not of host history.
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

**D3 — Native `community.general.ipa_getkeytab` with LDAP bind + `force`.**

```yaml
- name: "… export the kubeclusteradm keytab (native, forced, ticketless)"
  community.general.ipa_getkeytab:
    principal: "{{ ipa_kubeclusteradm_principle }}"
    path: /tmp/kubeclusteradm.keytab
    bind_dn: "uid=admin,cn=accounts,{{ company_domain | regex_replace('.', ',dc=') | regex_replace('^', 'dc=') }}"
    bind_pw: "{{ company_realm_password }}"
    force: true
    become: true
```

- `force: true` = delete-then-recreate → append-shadowing is impossible (the spec invariant becomes structural, not a shell chore).
- `bind_dn`/`bind_pw` = the export runs over LDAP as the admin principal → **no Kerberos ticket at all**; the `kinit admin` bootstrap task is deleted outright.
- Change reporting becomes truthful: changed when the block runs (file replaced/created), no change when the rotation block is skipped in steady state — the blanket `changed_when: true` retires.
- *Rejected*: keep `ipa-getkeytab` in shell with an env'd scratch ticket — works, but inferior; the native module exists for exactly this and the monorepo rule says native first.

**D4 — Drop the `kinit` line in the `ipa-kube-admin-credential.yml` cpw task.**
`kadmin.local -p` is a local DB operation — no ticket. The cpw task's `kinit admin` has no downstream consumer (verified: the only ticket consumer in the file is the verify task, which gets its own scratch cache). Dead weight today, gone after the change.

**D5 — Ticket tasks report no change.**
`krb_ticket` tasks carry `changed_when: false`: a scratch cache is ephemeral state, in the same class as the monorepo rule's existing `kinit` credential-renewal tolerance ("renews the credential cache only, no persistent state"). Idempotence: pre-clear + re-acquire → no reported change, no churn.

**D6 — Shell `ipa` CLI consumers stay shell, gain `env`.**
The installed `freeipa.ansible_freeipa` ships no CA/CA-ACL/certprofile modules (per the existing task-file comments), so consumer commands stay `command`/`shell` with `env: KRB5CCNAME` attached. The monorepo AGENTS.md `kinit` exception entry stays for the other roles (`tcharl.freeipa_server`, `tcharl.ansible_securehost`, `tcharl.nfs_server`); this role stops contributing usage sites.

**D7 — Cache location `/tmp`, same exposure class as today.**
The scratch caches hold the same material as today's `~/.k5.root` (host/service tickets, admin ticket). `/tmp` with `become: true` is root-readable — the same class as a root home cache. Optional hardening (0600 on the cache files) is a follow-up, out of scope.

## Stale-comment finding (S1)

The S1 safeguard comment says the shell `ipa` calls in the CA chain "run as root without a ticket" on the loop host (master) — but every shell `ipa` task in the chain (`ipa-ca-ensure.yml`, `ipa-ca-profile.yml`, `ipa-ca-link-profile.yml`) is **delegated to idm** and consumes idm's ticket (S3). No master-side ticket consumer exists. S1 is retained as a safeguard (converted to scratch) and its comment is corrected to match reality. *Follow-up (out of scope)*: consider deleting S1 entirely once convergence confirms nothing master-side needs a ticket.

## Risks

- **`krb_ticket` keytab+cache composition** — the module runs `kinit [-t <keytab>] [-c <cache>] [principal]`. Verify on the VM that keytab-only (no `principal`) + `cache_name` mints the keytab's first entry into the cache (S1, S5, S7 probes).
- **`ipa-getkeytab --binddn --bindpw` support** — the bind mode requires `freeipa-client` with the flags (long-standing, but unverified here); verify on idm at convergence.
- **`freeipa-client` on idm** — probes/ticketing on idm need `krb5` + `freeipa-client`; already present (IPA server hosts ship the client; today's shell `kinit` on idm proves it).
- **`env` on delegated tasks** — `env` applies on the delegation target; first converge is the proof (the E loop task is delegated; its `env` must reach idm).
- **Admin bind DN** — no existing `admin_dn` variable; derived from `company_domain` (`osgiliath.test` → `dc=osgiliath,dc=test`): `uid=admin,cn=accounts,dc=osgiliath,dc=test`. Verify against the actual DN on idm (`id -n admin`) during convergence.
- **`krb5.conf` on idm** — `KRB5CCNAME` must resolve against the same realm config as today's ambient flow (same host, same config — no change).

## Migration

No state migration: scratch caches are fresh by construction (pre-cleared); ambient caches are left in place (untouched — other flows and other roles may still use them). Behavioral equivalence: consumer commands unchanged; only the ticket source moves from ambient to scratch. First converge after the change is the proof; `destroy` re-runs the delete-flow (S8) from scratch on each cycle.
