# Proposal

## Why

The `principals-in-place` reordering left three kinds of residue a post-change audit found: one hole in the admin-password confinement invariant (`tasks/ipa-certs.yml` mints an `admin` TGT with the realm password **on the master**, missed by the static gate because it only audits `ipaadmin_password` module params), five identical `host/<master>` keytab tickets minted once per cert file where the runtime renewal script already proves one shared ticket suffices, and a duplicated `kubeclusteradm` keytab-usability probe plus ~130 lines of pre-clear+`krb_ticket` boilerplate across 14 task files. Cleaning this now keeps the ticketing layer coherent while the reordering is fresh, before the duplicates become the pattern new tasks copy.

## What Changes

- Convert the two `ipa ca-show` CA downloads in `tasks/ipa-certs.yml` to the established delegated-to-idm + `slurp` + `copy: content:` shuttle (the pattern already used by `tasks/kube-install-join-node.yml`); delete the master-side `admin.ca_fetch` scratch ticket. The admin password is then never delivered to any kube host, in any form.
- Extend the ticketing static gate to flag any `community.general.krb_ticket` carrying a `password:` (not just `ipaadmin_password` params) whose acquisition is not delegated to the IPA server.
- Mint one `host_master.cert_enroll.ccache` ticket at the head of the `tasks/ipa-certs.yml` cert-enrollment chain and share it across the five cert files (`kube-apiserver-kubelet-client`, `ipa-scheduler-client`, `ipa-controller-manager-client`, `ipa-front-proxy`, `ipa-api-server`), replacing five per-file pre-clear+acquire pairs. The host keytab is static mid-converge, so per-file re-mints add KDC round-trips and task noise without freshness value.
- Extract the `kubeclusteradm` keytab-usability probe (block/rescue `krb_ticket` → usable fact) into one shared include called by both `tasks/ipa-kube-admin-credential.yml` (`keytab_probe`) and `tasks/ipa-cert-renewal.yml` (`rotation_probe`); both call sites are kept so each phase still probes the keytab's current state before gating its own action.
- Extract the pre-clear + `krb_ticket` boilerplate into a shared include (principal, keytab/password, purpose cache, delegation target as vars), following the `tasks/ipa-ca-acl-host.yml` precedent, and reuse it at all ticketing call sites.
- Fix doc rot: the stale "scratch cache under /tmp" comment in `tasks/ipa-kube-admin-credential.yml`, and the monorepo `AGENTS.md` claim of "four orphaned task files" (an audit sweep finds zero orphans).
- No changes to cert subjects, CAs, profiles, the renewal schedule, or any ticket's principal — this is deduplication and hygiene, not re-behavioring.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `kerberos-ticketing`: (1) the realm-admin-password confinement requirement is strengthened to cover ticket acquisition itself — no `krb_ticket` minting an `admin` ticket with the realm password may run targeted at a kube host; (2) new requirement that a purpose phase mints one scratch ticket per (principal, host, credential source) and shares it across the tasks of that phase instead of re-minting per task file.

## Impact

- Task files: `tasks/ipa-certs.yml` (CA downloads, shared host ticket), `tasks/ipa-front-proxy.yml`, `tasks/ipa-api-server.yml`, `tasks/ipa-scheduler-client.yml`, `tasks/ipa-controller-manager-client.yml`, `tasks/kube-apiserver-kubelet-client.yml` (consume shared ticket), `tasks/ipa-kube-admin-credential.yml`, `tasks/ipa-cert-renewal.yml` (shared probe include), plus the pre-clear/acquire pairs at the remaining ticketing sites replaced by the shared ticket include.
- New shared includes under `tasks/` (or `files/`): `_krb_ticket.yml`, `_probe-kubeclusteradm-keytab.yml`.
- Test/audit: scratchpad static-gate script extended with the `password:`-ticket delegation check; the molecule verify suite (71 tests) is the behavioral gate.
- Docs: role `AGENTS.md` ticketing section (shared-ticket convention), monorepo `AGENTS.md` orphan-file claim, stale `/tmp` comment.
- Dependency: builds on the not-yet-archived `principals-in-place` delta for `kerberos-ticketing`; the two changes must archive in that order (principals-in-place first).
