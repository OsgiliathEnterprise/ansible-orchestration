# Tasks

## 1. Static gate and shared includes (foundation)

- [x] 1.1 Commit the extended static gate as `tests/static_gate.py` in the role (design D5: YAML-parsed checks a–f — shell kinit/klist/kdestroy, `/tmp` ccaches, non-delegated `ipaadmin_password`, **new** privileged `krb_ticket password:` not delegated to idm, task-file orphan check with `main.yml` exempt, unconsumed `register:`). Verify: running it with `.tox/converge-monorepo/bin/python tests/static_gate.py` on the CURRENT tree reports exactly the known `admin.ca_fetch` violation in `tasks/ipa-certs.yml` (proves the new check bites) and no false positives on checks a/b/c/e/f.
- [x] 1.2 Create `tasks/_krb_ticket.yml` (design D4): vars `krb_ticket_principal`, `krb_ticket_cache_purpose`, optional `krb_ticket_keytab_path` (⇒ keytab mode), optional `krb_ticket_password` (⇒ `no_log: "{{ secure_logs }}"` derived automatically), optional `krb_ticket_delegate_to`; always pre-clears `{{ kube_scratch_cache_dir }}/<principal-slug>.<purpose>.ccache` with the same delegate/become as the acquire, `changed_when: false`. Verify: `yamllint`/`ansible-lint` clean on the file; behavior exercised by group 2–5 call-site conversions.
- [x] 1.3 Create `tasks/_probe-kubeclusteradm-keytab.yml` (design D3): block/rescue `krb_ticket` keytab probe delegated to idm into `kubeclusteradm.{{ probe_purpose }}.ccache`, sets `{{ probe_fact_name }}` true/false. Verify: lints clean; behavior exercised by the group 4 call-site conversion.

## 2. F1 — Confine the realm admin password (correctness)

- [x] 2.1 Convert the two `ipa ca-show --certificate-out` downloads in `tasks/ipa-certs.yml` to the delegated-to-idm + `slurp` + `copy: content:` shuttle (pattern from `tasks/kube-install-join-node.yml`), with the delegated admin ticket acquired on idm via `_krb_ticket.yml` and the idm temp file removed afterwards; delete the master-side `admin.ca_fetch` pre-clear + `krb_ticket` pair. Keep the fingerprint-verification task master-local. Verify: `tests/static_gate.py` check (d) passes (zero privileged `password:` tickets targeted at kube hosts); `grep -n "admin.ca_fetch" tasks/` is empty; converge log shows the two CA files landing at their master paths via `copy: content:`.

## 3. F2 — One shared host ticket for the cert-enrollment phase

- [x] 3.1 In `tasks/ipa-certs.yml`, mint one `host_master.cert_enroll.ccache` ticket (via `_krb_ticket.yml`, keytab `/etc/krb5.keytab`) after the CA/ACL provisioning includes and before the first cert-file include. Verify: task appears once in converge output with `changed_when: false` semantics (ok, not changed, on steady-state runs).
- [x] 3.2 Remove the per-file pre-clear + acquire pairs from `tasks/kube-apiserver-kubelet-client.yml`, `tasks/ipa-scheduler-client.yml`, `tasks/ipa-controller-manager-client.yml`, `tasks/ipa-front-proxy.yml`, `tasks/ipa-api-server.yml`; their `ipacert`/consumer tasks inherit `env: KRB5CCNAME` pointing at the shared cache. Verify: `grep -c "krb_ticket" tasks/<each-file>.yml` is 0 for the five files; converge issues all five certs successfully (verify suite cert asserts stay green in group 6).
- [x] 3.3 Add the stale-cache sweep in `tasks/requirements.yml` removing the five superseded cache names (`host_master.{front_proxy,apiserver,scheduler,controller_manager,kubelet_client}.ccache`). Verify: after a converge on the existing VMs, `ls /run/krb5cc` on the master contains only current-convention cache names.

## 4. F3 — Single keytab-usability probe implementation

- [x] 4.1 Replace the inline probe blocks in `tasks/ipa-kube-admin-credential.yml` (`probe_purpose: keytab_probe`, `probe_fact_name: kca_keytab_usable`) and `tasks/ipa-cert-renewal.yml` (`probe_purpose: rotation_probe`, `probe_fact_name: kca_rotation_keytab_usable`) with `include_tasks: _probe-kubeclusteradm-keytab.yml`; keep both call sites. Verify: both facts still drive their downstream gates (password fallback / keytab re-export) — converge on a state where the keytab is valid shows both probes ok and re-export skipped; a forced-rotation scenario (delete the idm keytab file before converge) still triggers re-export.

## 5. F4 — Collapse remaining ticket boilerplate onto `_krb_ticket.yml`

- [x] 5.1 Replace every remaining pre-clear + `krb_ticket` pair in `tasks/` (remaining sites: `ipa-cert-renewal.yml`, `kube-install-join-node.yml`, `admin-user.yml`, `ipa-kube-admin-credential.yml`, `ipa-ca-acl-prejoin.yml`, `delete-ipa-cleanup.yml`, `requirements.yml`, others found by `grep -rn "community.general.krb_ticket" tasks/`) with `_krb_ticket.yml` include calls, preserving each site's principal, purpose cache name, keytab/password mode, and delegate target. Verify: `grep -rn "community.general.krb_ticket" tasks/` matches only `tasks/_krb_ticket.yml` and `tasks/_probe-kubeclusteradm-keytab.yml`; all distinct-purpose caches keep their `<principal>.<purpose>.ccache` names.
- [x] 5.2 Fold the verbatim-duplicated ACL-grant wrapper (pre-ticket + `ipa_ca_acl_host` loop) shared by `tasks/ipa-ca-acl-prejoin.yml` and `tasks/ipa-cert-renewal.yml` into one shared include following the `ipa-ca-acl-host.yml` precedent, both files including it. Verify: both files still grant both CA ACLs (converge log shows the grants once per phase); no behavioral diff in `ipa caacl-show` state after converge.

## 6. Documentation

- [x] 6.1 Fix doc rot: stale "scratch cache under /tmp" comment at `tasks/ipa-kube-admin-credential.yml:38` → `/run/krb5cc`; monorepo `AGENTS.md` "four orphaned task files" claim → current state (zero orphans, `tests/static_gate.py` orphan check as standing guard). Verify: `grep -rn "/tmp" tasks/ | grep -i ccache` shows only the intentional legacy-keytab-cleanup lines in `ipa-cert-renewal.yml`; monorepo `AGENTS.md` no longer claims four orphans.
- [x] 6.2 Update role `AGENTS.md` Kerberos Ticketing section: shared-phase-ticket rule (D2), `_krb_ticket.yml` / `_probe-kubeclusteradm-keytab.yml` as the single acquisition/probe entry points, privileged-password-ticket delegation rule, `tests/static_gate.py` as the committed gate; update the L3 task-flow graph with the two new includes and the phase-ticket position. Verify: graph lines match `grep -n include_tasks tasks/ipa-certs.yml` output; every listed include exists on disk.

## 7. Integration verification

- [x] 7.1 Run `tests/static_gate.py` — all checks a–f report zero findings.
- [x] 7.2 Full molecule cycle on parallels (macOS host): `tox -e destroy`, `converge-monorepo`, `verify-monorepo` — converge `failed=0` on all hosts, verify suite 71/71 green.
- [x] 7.3 Idempotence pass: re-converge + re-verify on the same VMs — `failed=0`, no unexpected changed tasks in the ticketing chain, verify suite 71/71 green. Live check: on the master, `ls /run/krb5cc` shows exactly one enrollment-phase host cache and no superseded `host_master.<per-file>` names.
- [x] 7.4 Same tests for '-sequential' if you are on an OS that supports this molecule scenario.

## Workflow follow-up

- Archive `principals-in-place` FIRST (this change's delta builds on its spec baseline), then archive `ticket-dedup-hygiene` via `/opsx-archive`; confirm `openspec list --specs` shows the strengthened `kerberos-ticketing` requirements absorbed.
- Run `/update-platform-docs` if any touched variables or paths surface in the generated doc blocks.
