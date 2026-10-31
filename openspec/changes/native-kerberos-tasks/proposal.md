## Why

The role acquires Kerberos tickets through ambient shell `kinit` in six task files (`ipa-certs.yml`, `ipa-kubernetes-ca.yml`, `kube-install-join-node.yml`, `ipa-kube-admin-credential.yml`, `ipa-cert-renewal.yml`, `delete-ipa-cleanup.yml`), relying on the default per-user cache (`~/.k5.<user>`). Three fragilities:

1. **Stale/expired ambient tickets** — `kinit` skips acquisition when a cache already exists. A cache holding a 10-hour ticket that has since expired is silently reused, and the downstream `ipa`/`ipa-getkeytab` call fails with an opaque ticket-expired error.
2. **Cross-flow pollution** — flows share one ambient cache per user (on idm: bootstrap, join, renewal, rotation, and delete all touch `~/.k5.root`; on master: safeguard + CA check). A ticket left behind by one flow — possibly for a different principal — becomes the input of the next.
3. **Append-shadowing in rotation** — the renewal flow appends `kubeclusteradm` to a *persistent* keytab that may already hold a stale entry for the same principal (the `kube-cert-renewal` spec forbids appending); today the shell `rm -f` + `ipa-getkeytab` dance is the only thing preventing it.

Additionally, the `ipa-pki-infra` spec scenario ("scratch ticket cache holds the admin principal's ticket") describes behavior the code does not actually implement — the code uses the ambient cache.

## What Changes

- **Scratch ticket caches** — every `kinit` becomes a `community.general.krb_ticket` task that acquires into a dedicated `cache_name` under `/tmp`, preceded by a pre-clear (`file: state=absent`) so a stale/expired ticket can never be reused. Downstream shell consumers inherit the cache via `env: KRB5CCNAME` (including on delegated tasks). Consumer commands themselves are unchanged.
- **Native keytab usability probes** — the two keytab probes (admin-credential keytab-first, renewal rotation) become `krb_ticket: keytab: true` block/rescue probes into scratch caches. Usable keytab mints a fresh ticket; a rotated keytab fails; neither probe reads or writes the ambient cache.
- **Native keytab export** — the rotation flow's `kinit admin` + `ipa-getkeytab` + `rm -f` shell sequence becomes a single `community.general.ipa_getkeytab` task (LDAP bind via `bind_dn`/`bind_pw`, `force: true`). No Kerberos ticket is needed, appending is impossible, and change reporting becomes truthful (changed when replaced, no change when the rotation block is skipped in steady state).
- **Spec** — new `kerberos-ticketing` capability: fresh scratch acquisition, keytab usability probes, native forced export.

## Capabilities

### New Capabilities
- `kerberos-ticketing`: scratch-cache ticket acquisition, keytab usability probes, native forced keytab export

### Modified Capabilities
(none — the existing `ipa-pki-infra` scenario wording already describes the target behavior; the code is what lags behind)

## Impact

- **Affected code**: `tasks/ipa-certs.yml`, `tasks/ipa-kubernetes-ca.yml`, `tasks/kube-install-join-node.yml`, `tasks/ipa-kube-admin-credential.yml`, `tasks/ipa-cert-renewal.yml`, `tasks/delete-ipa-cleanup.yml`, plus `env` on the idm-delegated `ipa` CLI consumers in the CA chain (`tasks/ipa-ca-ensure.yml`, `tasks/ipa-ca-profile.yml`, `tasks/ipa-ca-link-profile.yml`)
- **Dependencies**: `community.general` only (already pinned in `requirements-collections.yml`; both `krb_ticket` and `ipa_getkeytab` are present in the installed collection). No new dependencies.
- **Behavioral equivalence**: consumer commands unchanged; only the ticket source moves from ambient to scratch. Ticket tasks report no change (matching today's `changed_when: false` semantics — a ticket cache is ephemeral state, like the existing credential-cache renewal).
- **Docs**: monorepo AGENTS.md `kinit` exception note — the entry stays (other roles — `tcharl.freeipa_server`, `tcharl.ansible_securehost`, `tcharl.nfs_server` — still use shell `kinit`), but this role stops contributing usage sites.
