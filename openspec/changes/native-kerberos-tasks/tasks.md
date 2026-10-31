## 1. Pre-verification (read-only, on a running VM)

- [ ] 1.1 Confirm S1 has no master-side ticket consumer: every shell `ipa` task in the CA chain (`ipa-ca-ensure.yml`, `ipa-ca-profile.yml`, `ipa-ca-link-profile.yml`) is idm-delegated; `ipa-master.yml`/`ipa-api-server.yml`/`kube-apiserver-kubelet-client.yml`/`ipa-front-proxy.yml`/`ipa-controller-manager-client.yml`/`ipa-scheduler-client.yml` contain no shell `ipa` CLI calls
- [ ] 1.2 Verify `krb_ticket` keytab-only + `cache_name` composition on the VM: `kinit -t <keytab> -c <cache>` (no principal) mints the keytab's first entry into the cache (S1/S5/S7)
- [ ] 1.3 Verify `ipa-getkeytab --binddn --bindpw` support on idm (`freeipa-client` version)
- [ ] 1.4 Verify the derived admin bind DN on idm (`id -n admin` → `uid=admin,cn=accounts,dc=osgiliath,dc=test`) against the `company_domain`-derived construction
- [ ] 1.5 Confirm no downstream consumer of the `ipa-kube-admin-credential.yml` cpw task's `kinit` (D4)

## 2. Ticketing conversions (scratch caches)

- [ ] 2.1 `ipa-certs.yml` (S1): pre-clear + `krb_ticket: keytab: true, keytab_path: /etc/krb5.keytab, cache_name: /tmp/.ipa_certs_host.ccache, changed_when: false`
- [ ] 2.2 `ipa-certs.yml` (S2): pre-clear + `krb_ticket: principal: admin, password: {{ company_realm_password }}, cache_name: /tmp/.ipa_certs_admin.ccache, changed_when: false`; `env: KRB5CCNAME` on the 2 `ca-show` shell tasks; drop the `kinit` lines
- [ ] 2.3 `ipa-kubernetes-ca.yml` (S3): pre-clear + `krb_ticket: principal: admin, password: …, cache_name: /tmp/.ipa_k8s_ca_admin.ccache, changed_when: false`; `env: KRB5CCNAME` on the idm-delegated `ipa` consumers in the chain (`ipa-ca-ensure.yml`, `ipa-ca-profile.yml`, `ipa-ca-link-profile.yml`)
- [ ] 2.4 `kube-install-join-node.yml` (S4): pre-clear + `krb_ticket: principal: admin, password: …, cache_name: /tmp/.join_node_admin.ccache, changed_when: false`; `env: KRB5CCNAME` on the profile-gate and CA-fetch shell tasks; drop the `kinit` lines
- [ ] 2.5 `ipa-cert-renewal.yml` (S6): pre-clear + one `krb_ticket` before the loop (`/tmp/.renewal_admin.ccache`); `env: KRB5CCNAME` on the looped caacl shell task; drop both `kinit` lines
- [ ] 2.6 `delete-ipa-cleanup.yml` (S8): pre-clear + `krb_ticket: principal: admin, password: …, cache_name: /tmp/.cleanup_admin.ccache, changed_when: false`; `env: KRB5CCNAME` on the CA-check and ACL-check tasks; drop the `kinit` line
- [ ] 2.7 Correct the stale S1 comment (the chain's `ipa` consumers are idm-delegated, not master-side)

## 3. Keytab probes + native export

- [ ] 3.1 `ipa-kube-admin-credential.yml` (D probes): keytab-first probe → block/rescue `krb_ticket: keytab: true, keytab_path: /home/kubecreds/kubeclusteradm.keytab, cache_name: /tmp/.kca_keytab_probe.ccache` → `kca_keytab_usable`; password probe → block/rescue `krb_ticket: principal: admin, password: …, cache_name: /tmp/.kca_password_probe.ccache` → `kca_password_usable` (both `changed_when: false`, no ambient)
- [ ] 3.2 `ipa-kube-admin-credential.yml` (D rest): cpw task — drop the `kinit` line (`kadmin.local` is local); verify task — scratch cache (`/tmp/.kca_admin.ccache`) + `env` + `changed_when: false`
- [ ] 3.3 `ipa-cert-renewal.yml` (E probe): rotation keytab probe → block/rescue → `kca_rotation_keytab_usable` (`/tmp/.kca_rotation_probe.ccache`)
- [ ] 3.4 `ipa-cert-renewal.yml` (E rotation block): `community.general.ipa_getkeytab` (`principal`, `path: /tmp/kubeclusteradm.keytab`, `bind_dn`/`bind_pw` from `company_domain`/`company_realm_password`, `force: true`); delete the `kinit admin` bootstrap and `rm -f` tasks; retire the blanket `changed_when: true`

## 4. Spec + docs

- [ ] 4.1 `specs/kerberos-ticketing/spec.md` — ADDED: fresh scratch acquisition, keytab usability probes, native forced export
- [ ] 4.2 Confirm the `ipa-pki-infra` scenario wording is already at target (no delta needed)
- [ ] 4.3 Monorepo AGENTS.md — update the `kinit` exception note (the orchestration role no longer contributes usage sites; other roles do)
- [ ] 4.4 Role AGENTS.md — task-graph comments for the affected files (no graph change); note the scratch-cache pattern

## 5. Verification (monorepo cycle, parallels)

- [ ] 5.1 `tox -e lint` (yamllint + flake8 + ansible-lint)
- [ ] 5.2 `destroy` → `converge-monorepo`: S1–S8 all green; scratch caches exist and are consumed (`krb5cc_` inspection); consumer `ipa` calls succeed with env'd caches; verify task passes
- [ ] 5.3 `verify-monorepo`: full testinfra suite (join, rotation, kubectl)
- [ ] 5.4 `idempotence-monorepo`: ticket tasks report no change; rotation block skipped in steady state (no keytab churn)
- [ ] 5.5 `destroy` (reset path): S8 delete-flow tasks green (CA check + ACL check with the env'd scratch ticket)
