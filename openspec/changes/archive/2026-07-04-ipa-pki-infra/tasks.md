## 1. Gate Variable

- [x] 1.1 Add `use_ipa_pki: false` to `defaults/main.yml`

## 2. IPA PKI Sub-CA Setup (ipa-kubernetes-ca.yml)

- [x] 2.1 Add `use_ipa_pki` gate to all tasks in `ipa-kubernetes-ca.yml`
- [x] 2.2 Replace `kinit admin` shell auth with `kinit -kt /etc/krb5.keytab` safeguard task
- [x] 2.3 Fix `changed_when` for CA creation tasks (currently `changed_when: False`)
- [x] 2.4 Narrow CA ACL from `--hostcat=all --servicecat=all --usercat=all` to kubernetes-specific scope
- [x] 2.5 Ensure `kubeAdministrators` cert profile import has proper idempotency

## 3. Testinfra Tests

- [x] 3.1 Add test: `kubernetes-ca` exists in FreeIPA when `use_ipa_pki: true`
- [x] 3.2 Add test: `kubeAdministrators` cert profile exists when `use_ipa_pki: true`
- [x] 3.3 Add test: CA ACL exists and is linked to `kubernetes-ca`
- [x] 3.4 Update molecule converge vars: add `use_ipa_pki: true`
