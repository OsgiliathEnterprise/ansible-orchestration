# Proposal

## Why

Two idempotent setup tasks in `tasks/ipa-cert-renewal.yml` (the kubernetes-ca ACL host grant and the kubeclusteradm keytab generation) use `changed_when` expressions that reference bare result keys (`'ACL-GRANT-ADDED' in stdout`, `'KEYTAB-GENERATED' in stdout`) without a `register:` variable. Ansible only exposes module results to `changed_when`/`failed_when` through registered variables — bare result keys are never injected into the evaluation context, so both expressions fail with `'stdout' is undefined` and the tasks are marked failed even though the underlying command succeeds (rc=0). This aborts converge on ansible 14 / core 2.21 (the pinned version) and was reproduced identically on core 2.16 — i.e. it is not a version regression: these lines were added in `e748b99` ("chore: lint") and had never been live-tested before the post-rebuild converge that surfaced them. The failure is unrelated to the recent head.j2 DNS changes in `tcharl.freeipa_server` / `tcharl.ansible_securehost`; it reproduces with a bare local task (no loop, no delegate_to, no remote host).

## What Changes

- `tasks/ipa-cert-renewal.yml`: add `register:` to the two affected tasks and point their `changed_when` at the registered variable (`caacl_grant_result.stdout`, `kubeclusteradm_keytab_result.stdout`). Command logic is untouched.
- Spec: `kube-cert-renewal` gains a requirement that renewal setup derives its changed state from registered task results, so re-converging an already-converged cluster completes green with accurate per-item ok/changed reporting instead of failing on undefined variables.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `kube-cert-renewal`: adds a requirement that the idempotent renewal-setup tasks (CA ACL host grants, keytab generation) evaluate changed state from registered results — re-converge SHALL be green and report `ok` for already-satisfied items rather than failing with an undefined-variable error.

## Impact

- **Affected code**: one file — `tasks/ipa-cert-renewal.yml`, two tasks (lines 21–36 and 38–52). No target-host behavior changes; only Ansible-side change detection/reporting is corrected.
- **Verification**: local reproduction playbook (loop + delegate_to + no_log shape) proves the fixed idiom evaluates per-item and is idempotent on a second run; live proof requires the next converge cycle (`converge-monorepo`), which also unblocks `scoped-resolved-nameservers` task 4.2 ("converge is green").
- **No other occurrences**: a sweep of this role's tasks (and `tcharl.freeipa_server`, `tcharl.ansible_securehost`) found no other bare-result-key `changed_when`/`failed_when` expressions — the two expression-based usages in `drain-and-reset.yml` / `delete-configuration.yml` already use `register: res`.
