# Design

## Context

`principals-in-place` moved ticketing to owning hosts with a per-purpose scratch-cache convention (`/run/krb5cc/<principal>.<purpose>.ccache`, pre-cleared, module-acquired). A post-change audit found the convention applied with per-task-file granularity that produced duplicates, one missed delegation, and heavy boilerplate. Current-state facts this design builds on:

- `tasks/ipa-certs.yml` includes the five control-plane cert files in sequence (lines ~232–244); each one pre-clears + mints its own `host/<master>` ticket from `/etc/krb5.keytab` — five identical KDC round-trips per converge.
- The runtime renewal script (`templates/kube-cert-renew.sh.j2`) already authenticates all host-principal renewals of a tick with **one** host ticket — the converge-time shape is the outlier.
- `tasks/ipa-certs.yml` lines ~52–84 mint an `admin` TGT with `password: company_realm_password` **on the master** (no `delegate_to`) for two `ipa ca-show --certificate-out` shell consumers — the only remaining delivery of the realm password to a kube host. `tasks/kube-install-join-node.yml` already demonstrates the compliant shape: `ipa ca-show` delegated to idm + `slurp` + `copy: content:`.
- The `kubeclusteradm` keytab-usability probe (block/rescue `krb_ticket keytab: true` → usable fact) exists verbatim twice: `tasks/ipa-kube-admin-credential.yml` (`keytab_probe` → `kca_keytab_usable`) and `tasks/ipa-cert-renewal.yml` (`rotation_probe` → `kca_rotation_keytab_usable`).
- Precedent for shared parameterized includes exists: `tasks/ipa-ca-acl-host.yml` (var-driven, included by two files). Private inner includes use the `_…-inner.yml` naming under `tasks/`.
- Baseline spec: the `kerberos-ticketing` main spec is still the pre-refactor version; this change's delta builds on the `principals-in-place` delta (archive order: `principals-in-place` first).

## Goals / Non-Goals

**Goals:**
- Zero deliveries of the realm admin password to kube hosts in any module path (params or `krb_ticket password:`), enforced by an extended static gate.
- One shared scratch ticket per (principal, host, credential source) per purpose phase, converge-time and runtime shapes matching.
- Single shared implementations of the ticket-acquire and keytab-probe patterns; static, committed audit for the invariant greps.
- Documentation matching reality (role `AGENTS.md`, monorepo `AGENTS.md`, stale comments).

**Non-Goals:**
- No change to cert subjects, CAs, profiles, SAN gates, renewal schedule, or any ticket's principal.
- No merging of the distinct-purpose `admin` phase caches (`ca_provision`, `node_join`, `ca_acl`, `ipa_cleanup`, `ca_fetch`-replacement) — separate phases keep separate pre-cleared tickets by design; stale-ticket isolation is the point.
- No relocation of CSR/cert staging files under `/tmp` (`admin-user.yml` etc.) — the invariant covers tickets/keytabs; certs and CSRs are public.
- No removal of the transitional legacy `/tmp/kubeclusteradm.keytab` cleanup task in `ipa-cert-renewal.yml` (keep one release).
- No tox/CI wiring of the static gate script beyond documenting where to run it.

## Decisions

### D1 — CA downloads: delegated `ipa ca-show` + `slurp` + `copy: content:` shuttle
Convert both `ipa ca-show --certificate-out` tasks in `ipa-certs.yml` to run `delegate_to: idm` writing a root-only temp file on idm, then `slurp` (delegated) and `copy: content:` to the master's expected paths (`ca.crt.new`, `ca.crt.kubeclusteradm`), then remove the idm temp. Delete the master-side `admin.ca_fetch` pre-clear + `krb_ticket` pair; the delegated consumers authenticate with the idm-local admin ticket acquired via the shared ticket include (D4). The subsequent fingerprint-verification task stays on the master (reads the installed file, needs no ticket).
*Alternative rejected:* delegating only the `krb_ticket` but keeping master-local `ipa` consumers — `KRB5CCNAME` resolves on the host running the command, so a master-local `ipa` call cannot use an idm-local cache; and minting any admin-password ticket on the master is precisely the invariant hole being closed.

### D2 — One `host_master.cert_enroll.ccache` for the cert-enrollment phase
Mint one ticket (`host/<orchestration_host_hostname>`, keytab `/etc/krb5.keytab`) at the head of the enrollment chain in `ipa-certs.yml` — after the CA/ACL provisioning includes, before the first cert-file include. The five cert files drop their pre-clear + acquire pairs and their `ipacert`/consumer tasks inherit the cache via `env: KRB5CCNAME` as today. Naming keeps the convention: `<principal>.<purpose>.ccache` with purpose = the phase (`cert_enroll`), matching the runtime script's single-ticket shape.
Acquisition is unconditional (not gated on "any cert missing"): a keytab kinit is cheap, `changed_when: false`, and gating would re-add per-file conditionals — the duplication this removes.
*Alternative rejected:* status quo five per-file tickets — five identical KDC round-trips, and diverges from the runtime shape.
Stale-name sweep: `tasks/requirements.yml` gains one cleanup removing the five superseded cache names (`host_master.{front_proxy,apiserver,scheduler,controller_manager,kubelet_client}.ccache`) — old tmpfs files otherwise persist until reboot (harmless but violates the spirit of "cache set = current convention").

### D3 — Shared keytab-probe include, both call sites kept
New `tasks/_probe-kubeclusteradm-keytab.yml`: block/rescue `krb_ticket` (`keytab: true`, `keytab_path: {{ kube_idm_keytab_path }}`, `principal: {{ ipa_kube_admin_principal }}`) delegated to idm into `{{ kube_scratch_cache_dir }}/kubeclusteradm.{{ probe_purpose }}.ccache`, setting `{{ probe_fact_name }}` true/false. Called by `ipa-kube-admin-credential.yml` (`probe_purpose: keytab_probe`, `probe_fact_name: kca_keytab_usable`) and `ipa-cert-renewal.yml` (`probe_purpose: rotation_probe`, `probe_fact_name: kca_rotation_keytab_usable`).
Both calls stay: each phase must probe the keytab's **current** state right before gating its own action (password-fallback choice vs. re-export decision), and the admin-credential phase may change keytab state between the two probes.
*Alternative rejected:* single probe + fact reuse in `ipa-cert-renewal.yml` — saves ~5 tasks but couples the two phases' freshness semantics for negligible gain.

### D4 — Shared ticket-acquisition include `tasks/_krb_ticket.yml`
Vars: `krb_ticket_principal`, `krb_ticket_cache_purpose` (name-composed as `<principal-slug>.<purpose>.ccache` under `kube_scratch_cache_dir`), optional `krb_ticket_keytab_path` (presence ⇒ keytab mode), optional `krb_ticket_password` (⇒ `no_log: "{{ secure_logs }}"` automatically), optional `krb_ticket_delegate_to` (default: inventory host). The include always pre-clears the cache, acquires with `changed_when: false`, `become: true`. Every existing pre-clear + `krb_ticket` pair (21 sites) is replaced by one include call. The include itself is the enforcement point for the convention (pre-clear present, `changed_when: false`, no ambient cache).
*Alternative rejected:* leaving the 6-line pairs inline — the audit found the repetition drift-prone (it is exactly where the stale `/tmp` comment and the missed delegation survived).
Note on `ansible.builtin.file: state: absent` pre-clear inside the include: same `delegate_to`/`become` as the ticket task, no separate public task.

### D5 — Committed static gate script `tests/static_gate.py`
Extend the audited checks into a committed script under the role: (a) no shell `kinit|klist|kdestroy` in `tasks/`; (b) no `.ccache` under `/tmp` in `tasks/`; (c) no `ipaadmin_password` on non-idm-delegated kube-host tasks; (d) **new:** every `community.general.krb_ticket` carrying `password:` that mints a privileged principal (`admin`, or a principal containing `kubeclusteradm`) is `delegate_to` the idm group — YAML-parsed, not grep, per repo practice; (e) every `tasks/*.yml` referenced by an `include_tasks`/`import_tasks` (orphan check, with `main.yml` exempt); (f) every `register:` consumed. Invoked from the change's verification step and documented in role `AGENTS.md`; not wired into tox (Non-Goal).

### D6 — Documentation corrections
- `tasks/ipa-kube-admin-credential.yml:38` comment: "scratch cache under /tmp" → `/run/krb5cc`.
- Monorepo `AGENTS.md`: replace the stale "four orphaned task files … must be deleted" example with the current state (zero orphans; the `tests/static_gate.py` orphan check is the standing guard).
- Role `AGENTS.md`: Kerberos Ticketing section gains the shared-phase-ticket rule (D2), the `_krb_ticket.yml` / `_probe-kubeclusteradm-keytab.yml` includes as the single acquisition/probe entry points, and the privileged-password-ticket delegation rule; L3 task-flow graph gains the two new includes and the phase-ticket position.

## Risks / Trade-offs

- [Shared enrollment ticket is minted even when every cert already exists] → one keytab kinit per converge, `changed_when: false`, no drift; strictly fewer KDC calls than today's five.
- [Host keytab rotated mid-converge would leave the shared cache stale] → no flow in this role rotates `/etc/krb5.keytab` during converge; assumption documented in role `AGENTS.md`.
- [Shared-include refactor changes task names in converge logs] → the verify suite asserts files/commands/certs, not task names; converge-log greps in this change use new names.
- [`_krb_ticket.yml` include hides `no_log` behavior behind a var] → the include derives `no_log` from password-mode presence, so a password flow cannot forget it; static gate (d) cross-checks password tasks anyway.
- [Delta builds on not-yet-archived `principals-in-place` baseline] → archive order is fixed: `principals-in-place` first; both deltas touch the same requirement headers and `openspec validate` runs after each edit.
- [Stale-cache sweep deletes files that may not exist] → `file: state: absent` is idempotent `ok`.

## Migration Plan

Pure converge-side change: re-converge the existing molecule VMs (`converge-monorepo`) → `verify-monorepo` (71 tests green is the gate) → static gate script green → idempotence re-converge/re-verify. No VM destroy needed for validation (no IPA-side state changes), but the final full `destroy → converge → verify` clean cycle follows the role's standard gate before archiving. Rollback = revert the role commit; no persistent state depends on the removed per-file caches beyond tmpfs.

## Open Questions

None.
