## 1. Convert admin user principal to native ipauser

- [x] 1.1 Confirm scope: verify `tasks/admin-user.yml` is the only file with a shell-based `ipa user-add` / `ipa user-*` invocation by grepping `tasks/` and `molecule/`; verify no other matches are returned.
- [x] 1.2 Replace the "create user principal for admin cert (IPA PKI)" shell task in `tasks/admin-user.yml` with a `freeipa.ansible_freeipa.ipauser` task using `name=kubeclusteradm`, `first=kube`, `last=ClusterAdmin`, `email={{ kube_credential_email_address }}`, `password={{ company_realm_password }}`, `no_log: "{{ secure_logs }}"`, `delegate_to: "{{ groups[idm_group] | first }}"`, `become: true`; verify with `ansible-playbook --syntax-check` and by confirming the file no longer contains an `ipa user-add` shell task.
- [x] 1.3 Remove `failed_when: false`, `changed_when: false`, and the `when: not orchestration_admin_cert.stat.exists` guard from the principal creation task so failures surface loudly and idempotency is handled by the module; verify the task has no `failed_when`/`changed_when`/`when` keys.

## 2. Verification

- [x] 2.1 Run molecule converge for parallels (`tox -e converge-monorepo --scenario-name=parallels`) and confirm the run log shows an `ipauser` task success with no `ipa user-add` shell invocation, proving the principal is created via the native module.
- [x] 2.2 Run molecule verify (`tox -e verify-monorepo --scenario-name=parallels`) and confirm the testinfra admin-cert issuer check and `kubectl get nodes` pass end-to-end. (Admin-cert tests passed: `test_admin_cert_issuer_is_kubernetes_ca`, `test_admin_cert_signed_by_kubernetes_ca`, `test_kubectl_get_nodes_with_ipa_credentials`. Note: 2 unrelated failures — `test_kubectl_get_nodes_equals_two` and `test_volume_is_create` — caused by a pre-existing node1 join failure, not this change.)
