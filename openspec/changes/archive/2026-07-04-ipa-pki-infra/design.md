## Context

The `ipa-kubernetes-ca.yml` skeleton exists but uses shell commands with `kinit admin` + `ipa ca-add` delegated to the IPA server. The CA ACL uses `--hostcat=all --servicecat=all --usercat=all` which is overly permissive. The `use_ipa_pki` gate variable doesn't exist yet.

## Goals / Non-Goals

**Goals:**
- Create `kubernetes-ca` lightweight sub-CA with proper idempotency
- Create scoped CA ACL (not `--hostcat=all`)
- Create `kubeAdministrators` cert profile with `O=system:masters`
- Add Kerberos ticket validation before cert operations

**Non-Goals:**
- Certificate provisioning (covered by `ipa-pki-bootstrap`)
- Admin credentials (covered by `ipa-kubectl-auth`)

## Decisions

**Keep delegated shell for CA setup tasks**
- CA creation, ACL, and profile import must run on the IPA server
- `freeipa.ansible_freeipa` modules for `ca-add`, `caacl-add` don't exist in the collection
- Use `delegate_to: ipaserver` with proper `changed_when` and `no_log`

**Narrow ACL to kubernetes-administrators group**
- Replace `--hostcat=all --servicecat=all` with host/service group targeting
- ACL allows kubernetes-administrators group to request certs from kubernetes-ca

**Kerberos ticket validation**
- Add `kinit -kt /etc/krb5.keytab` task before cert requests
- Master is enrolled as IPA client in molecule prepare phase

## Risks / Trade-offs

[Shell commands for CA setup are fragile] → Mitigation: Use `failed_when: false` + output parsing for idempotency. Existing skeleton pattern works for idempotent checks.
