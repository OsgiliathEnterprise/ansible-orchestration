## 1. Implement credential provisioning in ipa-kube-admin-credential.yml

- [x] 1.1 Add "activate kubeclusteradm password if KDC reports it expired" task between user creation and kinit verification: plain one-line `kinit` first; on failure retry with three lines of stdin (old + new + confirm, same value) driving the forced-change flow; `|| exit 1` guard so a failed second attempt cannot be masked — **superseded by 1.5/1.6: the three-line flow is fragile (fresh account is immediately expired AND inside the KDC min-password-age window "Too soon"; stored-key state after the flow observed unreliable). The activation task has been removed from the file.**
- [x] 1.2 Set `changed_when` on the activation task and keep `no_log: "{{ secure_logs }}"` consistent with sibling tasks — **superseded: change reporting now comes from the probe-gated `cpw` task (see 1.6)**
- [x] 1.3 Update the file header comment to document FreeIPA's immediately-expired API-set password behavior — **superseded by 1.8**
- [x] 1.4 Create the IPA user **without a password** (move the `ipauser` task from `admin-user.yml`, add the `email` attribute required by ipacert validation; keep `update_password: on_create` for re-converge attribute comparison)
- [x] 1.5 Add a one-line kinit **probe** task (password via stdin, `changed_when: false` — ticket cache only) printing `usable`/`missing`
- [x] 1.6 Add a `kadmin.local cpw` task on the IPA server (delegated to `{{ groups[idm_group] | first }}`, `become`, gated on probe `missing`) — no KDC changepw policy, no "Too soon", no expiry attribute stored
- [x] 1.7 Keep the one-line kinit verification and `kubectl get nodes` tasks unchanged
- [x] 1.8 Update the file header comment to document the revised design (no-password creation, `kadmin.local` key setting, idempotency, ordering before `admin-user.yml`)

## 2. Fix CSR SAN rejection in admin-user.yml

- [x] 2.1 Set `use_common_name_for_san: false` on the `openssl_csr` task (FreeIPA rejects DNS SANs on user principals — `ipaserver/plugins/cert.py`: DNS- and IP-type SAN entries are forbidden for user principals; the DN `commonName` must match the user's login, which the task satisfies via `common_name`)
- [x] 2.2 Add legacy CSR cleanup: read-only `openssl req -text` inspection of the CSR + `file: state: absent` on CSR and paired key when a `X509v3 Subject Alternative Name` section is present (ordered before key/CSR generation so a clean CSR is regenerated). **Mechanism note:** a `slurp` of the raw file — or of its `b64decode` — can never detect the SAN: the file is PEM (base64-encoded DER) and the extension name is only human-readable in `openssl req -text` output; no native module inspects CSR extensions (`community.crypto.x509_certificate_info` is certificate-only), so the inspection is a strictly read-only command (`changed_when: false`, `|| true` for the absent-file case)
- [x] 2.3 Remove the `ipauser` task from `admin-user.yml` (moved to `ipa-kube-admin-credential.yml`, which runs first) and update the header comment
- [x] 2.4 Replace the enrollment task's `community.crypto.openssl_certificate` with `freeipa.ansible_freeipa.ipacert` — the `ipa` provider was removed in community.crypto 2.0.0 (installed 3.5.0 supports only selfsigned/ownca/acme), so the module no longer exists and the task fails at resolution. The replacement follows the sibling files (`kube-node-cert.yml`, `ipa-api-server.yml`): `state: requested`, `csr_file`, `certificate_out`, `ca: kubernetes-ca`, `profile_id: kubeAdministrators`, `ipaadmin_password: company_realm_password`. The `principal` parameter takes the bare IPA username — `ipa_kube_admin_principal` (defaults: `kubeclusteradm`, no `@realm`: the module runs on the master, which is an IPA client and resolves the realm itself). Gate: `stat` on the cert file; `no_log: "{{ secure_logs }}"`

## 3. Verify

- [x] 3.1 Run lint gate (`tox -e lint`) in the role directory — 0 failures, 0 warnings (production profile); the `cpw` task gained an explicit `changed_when: true` (probe-gated, so not a blanket suppression)
- [x] 3.2 Full molecule cycle on `parallels`: destroy → converge-monorepo (fresh VM must pass kinit verification and CSR enrollment without manual intervention) → verify-monorepo
