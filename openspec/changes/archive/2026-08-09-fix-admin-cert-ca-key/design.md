## Context

`tasks/admin-user.yml:40-47` uses `community.crypto.x509_certificate` with the `ownca` provider, referencing `ca.key` which is the kubeadm-generated key replaced during IPA PKI swap. The admin cert must be IPA-signed like all other control plane certs.

## Goals / Non-Goals

**Goals:**
- Replace `ownca` signing with `freeipa.ansible_freeipa.ipacert` using `ca=kubernetes-ca`
- Add stat check to skip if `kubeadm.crt` already exists
- Add testinfra tests: admin cert is IPA-signed, kubectl can query the cluster

**Non-Goals:**
- Changing the admin cert CN or subject fields
- Modifying the existing CSR generation logic

## Decisions

- Follow the same pattern as `ipa-api-server.yml`: stat check → ipacert request with `ca=kubernetes-ca`
- Use `profile_id: kubeAdministrators` for consistency with other IPA-signed certs
- The CSR generation task (line 29-38) remains unchanged
- Add tests to `molecule/default/tests/test_master.py` using the existing testinfra pattern

## Risks / Trade-offs

- Must verify `company_realm_password` is available when the ipacert task runs (it is, via molecule converge files)
- The ipacert task delegates to the IPA server; ensure the `kubernetes-ca` exists before admin cert signing runs (it does, as IPA PKI infrastructure runs first)
