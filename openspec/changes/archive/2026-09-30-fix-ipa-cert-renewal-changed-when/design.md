# Design

## Context

See proposal.md for motivation. Current state that shapes this design:

- `tasks/ipa-cert-renewal.yml` has two idempotent setup tasks — "Grant kubernetes-ca access to all kube hosts" (lines 21–36, loop over masters+nodes, delegate_to idm) and "Generate kubeclusteradm keytab on idm" (lines 38–52). Both end with `changed_when: "'<MARKER>' in stdout"` but declare no `register:`.
- How Ansible evaluates these expressions (verified against core 2.16 source, `task_executor.py`: after the action runs, only `vars_copy[register] = result` feeds the result into the conditional context; bare result keys are never injected): a task's result is available to `changed_when`/`failed_when` **only through a registered variable**. Reproduced locally on both core 2.16 and core 2.21 (ansible 14, the pinned version) with a bare local task — no loop, no delegate_to, no remote host: `changed_when: "'X' in stdout"` and even `changed_when: "rc == 0"` fail with `'stdout' is undefined` / `'rc' is undefined`, while `register: res` + `changed_when: "'X' in res.stdout"` succeeds.
- The lines were added in `e748b99` ("chore: lint") and had never been live-tested; the post-rebuild converge that surfaced them was their first execution. The failure is unrelated to the head.j2 DNS changes in `tcharl.freeipa_server` / `tcharl.ansible_securehost`.
- The accompanying `[WARNING]: Module invocation had junk after the JSON data` (empty trailing content) is a separate cosmetic artifact of module-output parsing — the result parses fully and correctly; it does not cause or interact with this failure.

## Goals / Non-Goals

**Goals:**
- Both tasks evaluate changed state per loop item from their own result: already-satisfied items report `ok`, work-performing items report `changed`; re-converge is green.
- Command logic, loop, delegate_to, become, and no_log attributes stay byte-identical — no target-host behavior change.

**Non-Goals:**
- The cosmetic "junk after the JSON data" warning (out of scope; parsing succeeds).
- `no_log`/`secure_logs` semantics or masking behavior.
- Other tasks in the role — a sweep found no other bare-result-key conditionals (`drain-and-reset.yml` / `delete-configuration.yml` already use `register: res`).
- Upstream Ansible changes, version pinning, or monorepo-wide idiom migration.

## Decisions

**D1: `register:` + reference the registered variable in `changed_when`.** Verified on both core 2.16 and 2.21 with a replica of the exact task shape (loop + delegate_to + no_log): per-item evaluation works (`res` is the current item's result during each item's conditional evaluation) and a second run reports all items `ok`. Alternatives considered:
- `_task.result.stdout` — works on core 2.21 but is version-specific (not available on 2.16, which other monorepo roles pin); rejected for portability across the role matrix.
- `item.stdout` — wrong target: with loop + register, `item` is the loop value (the hostname string), not the result; verified failure ("object of type 'str' has no attribute 'stdout'" on 2.21).
- Drop `changed_when` and rely on module defaults — rejected: shell/command always report `changed=true`, so every converge would show churn, breaking accurate idempotency reporting (spec scenario "Re-converge … is green").

**D2: Register variable names follow the file's descriptive convention** (`kca_keytab_b64`): `caacl_grant_result` and `kubeclusteradm_keytab_result`. Nothing downstream consumes them — they exist solely for changed-state evaluation. With `secure_logs: Yes`, registered values are masked in later tasks, which is irrelevant here since nothing reads them; per-item `changed_when` evaluation happens before display-time masking (verified by code reading plus the local no_log replica run).

**D3: No command-logic changes.** The marker-echo pattern (`ACL-GRANT-PRESENT`/`ACL-GRANT-ADDED`, `KEYTAB-PRESENT`/`KEYTAB-GENERATED`) is kept as-is; only the evaluation wiring changes.

## Risks / Trade-offs

- [Live proof requires a rebuilt environment (currently destroyed)] → The local replica playbook covers the idiom's semantics (per-item, idempotent second run); live confirmation folds into the next converge cycle — the same cycle `scoped-resolved-nameservers` task 4.2 needs ("converge is green"), so no extra rebuild is required.
- [The cosmetic junk-after-JSON warning may still appear in output] → Accepted: it does not affect result parsing or change detection; chasing its source (invisible trailing bytes in the module stream) is a separate investigation if it ever becomes actionable.
- [Two active changes touch `tasks/ipa-cert-renewal.yml` (`scoped-resolved-nameservers` deletes the head.conf snippet; this change edits two tasks)] → Disjoint line ranges, no conflict; apply order is independent.

## Migration Plan

1. Edit `tasks/ipa-cert-renewal.yml`: add `register:` to both tasks and point each `changed_when` at its registered variable (D1/D2).
2. Verify: local replica playbook (loop + delegate_to + no_log shape) shows per-item changed/ok and an idempotent second run; `ansible-playbook --syntax-check` on the converge playbook passes.
3. Live confirmation on the next converge cycle (`converge-monorepo`, parallels): both tasks green, ACL-grant items report `changed` only for hosts actually added.
4. Rollback: revert the two task blocks (git checkout) — no target-host state to clean up; ACL grants and keytab generation are already idempotent by construction.

## Open Questions

None.
