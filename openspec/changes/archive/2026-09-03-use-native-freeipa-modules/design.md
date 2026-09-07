## Context

See `proposal.md` for motivation. The role already uses native `freeipa.ansible_freeipa.*` modules for most IPA operations (`ipacert` for certificate requests, `ipagroup` for group creation, `ipaservice`/`ipahost` for principals). The one remaining shell-based IPA mutation is the admin user principal: `tasks/admin-user.yml` runs `ipa user-add kubeclusteradm ... --password`, piping the realm password on stdin and masking all errors with `failed_when: false`.

The installed freeipa collection (`~/.ansible/collections/ansible_collections/freeipa/ansible_freeipa/plugins/modules/`) provides a native `ipauser` module whose parameters map directly onto the shell flags. This design converts that one task to the native module and documents which other IPA operations have **no** native module and therefore stay as shell.

## Goals / Non-Goals

**Goals:**
- Create the `kubeclusteradm` principal via `freeipa.ansible_freeipa.ipauser` instead of shell `ipa user-add`.
- Make a failed principal creation fail loudly (drop `failed_when: false`).
- Rely on module idempotency so re-runs are safe and report "already present".
- Document, with evidence from the installed collection, which IPA operations have no native module.

**Non-Goals:**
- Converting lightweight CA (`ca-*`), CA ACL (`caacl-*`), or certificate profile (`certprofile-*`) operations — no native modules exist for them (see Decisions D5).
- Changing the certificate request flow (`ipacert`) or group creation (`ipagroup`).
- Removing `kinit admin`, `ipactl restart`, or the `cert.py` SAN-reachability patch from `tasks/ipa-kubernetes-ca.yml`.

## Decisions

### D1: Use `freeipa.ansible_freeipa.ipauser` for the admin principal
The native module provides idempotency-by-name, structured error handling, and avoids putting the realm password in a shell string. Alternative considered — keep the shell task — rejected because it pipes the password on stdin, has no existence check, and swallows failures.

### D2: Parameter mapping from shell flags to module options
| Shell (`ipa user-add`) | Module option (`ipauser`) | Value |
|---|---|---|
| `kubeclusteradm` (positional) | `name` | `kubeclusteradm` |
| `--first=kube` | `first` | `kube` |
| `--last=ClusterAdmin` | `last` | `ClusterAdmin` |
| `--email={{ kube_credential_email_address }}` | `email` | `{{ kube_credential_email_address }}` |
| `--password` (stdin) | `password` | `{{ company_realm_password }}` |

The module's `email` option accepts a list; passing the single configured address is valid. Keep `no_log: "{{ secure_logs }}"` so the password is not echoed.

### D3: Drop error-swallowing and rely on idempotency
Remove `failed_when: false` and `changed_when: false`. The native module reports `changed`/`failed` correctly, so a real failure (e.g., bad credentials, LDAP down) now aborts the run instead of being masked. Also remove the `when: not orchestration_admin_cert.stat.exists` guard on this task: because the module is idempotent by name, it can safely run unconditionally and will create-if-missing / no-op-if-present. This makes the principal a guaranteed prerequisite for the downstream `ipacert` request regardless of cert state (the cert-request task keeps its own existence guard).

### D4: Preserve delegation and authentication
Keep `delegate_to: "{{ groups[idm_group] | first }}"` and `become: true`. The module authenticates with `ipaadmin_password`, so this task does **not** require a prior `kinit` (unlike the remaining shell-based CA/CAACL/certprofile commands, which still need their Kerberos ticket).

### D5: Operations that have no native freeipa module (stay as shell)
Verified against the installed collection's module list. The following have **no** corresponding `freeipa.ansible_freeipa.*` module and remain shell-based in `tasks/ipa-kubernetes-ca.yml` / `tasks/ipa-certs.yml`:

| Operation | Shell command(s) | Native module? |
|---|---|---|
| Lightweight CA create/check | `ipa ca-add`, `ipa ca-find`, `ipa ca-show` | No (`ipaca` does not exist) |
| CA ACL management | `ipa caacl-add`, `caacl-find`, `caacl-add-ca`, `caacl-add-profile` | No (`ipacaacl` does not exist) |
| Certificate profile mgmt | `ipa certprofile-show`, `-import`, `-find` | No (no certprofile module) |
| Kerberos ticket | `kinit admin` | No (module auth uses `ipaadmin_password`) |
| Service restart / source patch | `ipactl restart`, `cert.py` sed patch | No |

Documenting this prevents future maintainers from hunting for modules that do not exist. If the freeipa collection later ships CA/CAACL/certprofile modules, a follow-up change can convert those tasks.

## Risks / Trade-offs

- [Behavior change: failures now surface] A previously-masked `user-add` failure will now abort converge → Mitigation: this is intentional; if principal creation fails the downstream `ipacert` request would fail anyway. Verify with a molecule converge run and the testinfra admin-cert/kubectl tests.
- [Unconditional task execution] Removing the cert-existence guard means `ipauser` runs on every converge → Mitigation: the module is idempotent by name, so re-runs are no-ops; cost is one cheap API call.
- [Module version drift] `ipauser` parameter names could change across collection versions → Mitigation: the freeipa collection is already a hard dependency (used by `ipacert`/`ipagroup`); pinning/versioning is handled at the requirements level, not per-task.

## Migration Plan

Single-file edit to `tasks/admin-user.yml`: replace the shell "create user principal" task with an `ipauser` task and drop its error-swallowing/guard. No data migration. Rollback: revert the task to the previous shell form. Validate via `tox -e converge-monorepo --scenario-name=parallels` followed by `tox -e verify-monorepo` (admin-cert issuer check + `kubectl get nodes`).

## Open Questions

None — scope is bounded and verified against the installed collection's module list.
