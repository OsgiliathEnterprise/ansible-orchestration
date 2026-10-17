# Tasks

## 1. Fix changed_when wiring in ipa-cert-renewal.yml

- [x] 1.1 Add `register: caacl_grant_result` to the "Grant kubernetes-ca access to all kube hosts" task and change its `changed_when` from `'ACL-GRANT-ADDED' in stdout` to `'ACL-GRANT-ADDED' in caacl_grant_result.stdout`; verify with `grep -n "caacl_grant_result\|in stdout" tasks/ipa-cert-renewal.yml` showing the registered reference and no bare `stdout` conditional
- [x] 1.2 Add `register: kubeclusteradm_keytab_result` to the "Generate kubeclusteradm keytab on idm" task and change its `changed_when` from `'KEYTAB-GENERATED' in stdout` to `'KEYTAB-GENERATED' in kubeclusteradm_keytab_result.stdout`; verify with `grep -n "kubeclusteradm_keytab_result\|in stdout" tasks/ipa-cert-renewal.yml` showing the registered reference and no bare `stdout` conditional remaining anywhere in the file

## 2. Verification

- [x] 2.1 Run a local replica playbook (loop + delegate_to + no_log shape, marker-file idempotency) on the pinned ansible 14 / core 2.21 interpreter and verify first run reports per-item changed/ok against each item's own result while a second run reports all items `ok`
- [x] 2.2 Run `ansible-playbook --syntax-check molecule/parallels/converge.yml` (converge-monorepo tox env) and verify it passes with no errors
- [x] 2.3 On the next rebuilt parallels environment, run `tox -e converge-monorepo -- --scenario-name=parallels` and verify both renewal-setup tasks complete green — ACL-grant items report `changed` only for hosts actually added to kubernetes-ca-acl, keytab task reports `ok` when the keytab already exists — then re-run converge and verify both tasks report no change (spec scenarios "Re-converge on an already-converged cluster is green" and "Mixed state within one run evaluates per host")
