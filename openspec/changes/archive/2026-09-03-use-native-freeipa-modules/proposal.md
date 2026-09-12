## Why

The role creates the `kubeclusteradm` IPA user principal with a shell-based `ipa user-add` command (`tasks/admin-user.yml`) that pipes the realm password on stdin and swallows all errors (`failed_when: false`, `changed_when: false`). This is fragile — the password appears in a shell string, there is no idempotency check, and failures are silently ignored. It is also inconsistent with the rest of the role, which already uses native `freeipa.ansible_freeipa.*` modules for certificate requests (`ipacert`) and group creation (`ipagroup`). The freeipa collection ships a native `ipauser` module that should be used instead.

## What Changes

- Replace the shell-based `ipa user-add kubeclusteradm ... --password` task in `tasks/admin-user.yml` with the native `freeipa.ansible_freeipa.ipauser` module (`first=kube`, `last=ClusterAdmin`, `email`, `password`).
- Remove the now-unneeded error-swallowing (`failed_when: false`, `changed_when: false`) so a failed principal creation fails loudly instead of being masked.
- Document, in `design.md`, which IPA operations have **no** native freeipa module and therefore remain shell-based — lightweight CA (`ca-*`), CA ACL (`caacl-*`), and certificate profile (`certprofile-*`) — so maintainers do not hunt for modules that do not exist.

## Capabilities

### New Capabilities
<!-- None introduced by this change. -->

### Modified Capabilities
- `ipa-pki-bootstrap`: Add a requirement that the admin user principal (`kubeclusteradm`) is created via the native `freeipa.ansible_freeipa.ipauser` module rather than a shell-based `ipa user-add`, mirroring the existing "Certificate requests use ipacert module" requirement.

## Impact

- **Code**: `tasks/admin-user.yml` — the "create user principal for admin cert (IPA PKI)" task only.
- **Behavior**: The `kubeclusteradm` principal is now managed idempotently by the native module; a failed creation fails loudly instead of being silently swallowed. Downstream certificate request (`ipacert`) and group creation (`ipagroup`) are unchanged.
- **Out of scope (documented, not changed)**: Lightweight CA, CA ACL, and certificate profile operations in `tasks/ipa-kubernetes-ca.yml` remain shell-based because the freeipa collection provides no native modules for them.
