## Context

See proposal.md for motivation. Verified facts: `ipa-certs.yml` L59-64 already uses `ansible.builtin.replace` on the apiserver manifest (the style to extend); community.crypto is pinned at 3.3.0 (`requirements/requirements.txt`) and has no chain-validation module; `defaults/main.yml` is a flat variable file with no existing API host/port variables; the two kubectl tasks at L160-166 and L172-180 run identical commands (one `|| true`, one retried).

## Goals / Non-Goals

**Goals:**
- Replace every shell task in `ipa-certs.yml` that has a native equivalent, without changing what gets patched or where.
- Make readiness waits variable-driven and endpoint-based per the agreed convention (variabilize host/port/timeout, poll `/healthz` until ready).
- Keep the spec honest: correct the stale controller-manager/scheduler scenario text while touching these exact tasks.

**Non-Goals:**
- No change to the dual-CA design itself (bundle contents, which CA signs what) — that is change `ipa-kubernetes-ca-hardening` territory if it ever changes.
- No guard added for "only restart apiserver when certs actually changed" — both current and new trigger semantics restart on every converge; improving that is a separate behavioral change.
- No change to the ipacert-based cert issuance tasks (already native).

## Decisions

**D1: CA bundle via `slurp` ×2 + `copy content=`.**
Read `ca.crt.kubeadm` and `ca.crt.new`, write their concatenation to `ca-bundle.crt` with `owner: root, mode: '0644'`. Idempotent for free (content comparison), replacing the unconditional `changed_when: true`.
*Alternative considered:* keep shell cat — rejected; it is the canonical example of a non-idempotent shell task in this file.

**D2: `sed -i` ×3 → three `replace` tasks; scheduler guard dropped.**
Each substitution becomes its own `replace` task with flag-anchored regexps (`--client-ca-file=...`, `--cluster-signing-cert-file=...`, `--root-ca-file=...`) consistent with the existing L59-64 style. The scheduler's `grep -q` guard is deleted because `replace` reports ok (not failure) on no-match — the guard only existed to avoid a sed that would otherwise be a silent no-op, which `replace` already handles.
*Alternative considered:* one shell task with three seds — rejected; loses per-substitution change reporting and keeps the flagged pattern.

**D3: Readiness waits become variable-driven `/healthz` polls.**
New defaults: `kubernetes_api_host: "127.0.0.1"`, `kubernetes_api_port: 6443`, `kubernetes_api_ready_retries: 12`, `kubernetes_api_ready_delay: 10`. The L86-92 port `wait_for` becomes a `uri https://<host>:<port>/healthz` poll (`validate_certs: no`, liveness only — TLS trust is validated later by the kubectl task using admin.conf); the existing L139-148 healthz wait adopts the same variables. Per user decision: variabilize first, then loop until the service is actually up rather than fixed-delay raw-port waits.
*Alternative considered:* keep `wait_for` with variables — rejected; a listening port does not mean the API serves (kubelet may hold the socket during pod restart).

**D4: `touch` → `file state=touch`.**
Semantically equivalent for an existing static pod manifest (mtime update triggers kubelet restart). Note: both versions trigger a restart on every converge — preserved intentionally, not fixed here.
*Alternative considered:* guard with stat + cert-change detection — rejected as out-of-scope behavioral change.

**D5: `openssl verify` kept with exception comment.**
community.crypto 3.3.0 has no chain-validation module (`x509_certificate_info` parses fields only; it cannot validate that `apiserver.crt` chains to the new CA). The task keeps its retries/until and gains a comment stating why shell is required, per the exception rule codified in change `agents-md-practices-c4`.

**D6: Duplicate kubectl tasks consolidated.**
Keep one best-effort retried `kubectl --kubeconfig /etc/kubernetes/admin.conf cluster-info` (retries 3, delay 10, `failed_when: false`, registered) followed by a single debug print of its output. Delete the `|| true` duplicate and its separate register. Shell is kept because this validates admin.conf end-to-end — no native module reads a kubeconfig file (documented exception).

**D7: Spec delta corrects stale scenario text.**
The main spec's controller-manager/scheduler scenario claims configs reference `ca.crt`; the code patches to `ca-bundle.crt` / `ca.crt.kubeadm`. Since this change rewrites exactly these tasks, the delta fixes the wording (MODIFIED requirement, no behavioral change).

## Risks / Trade-offs

- [`replace` silently skips when a flag is absent from a manifest] → Same silent-skip property as the current seds; downstream healthz + kubectl verification catches a broken apiserver. Accepted equivalence, not a regression.
- [Bundle built by `copy content=` differs byte-wise from `cat` output] → Both are raw concatenation of the same two files; converge verification includes checking the bundle contains exactly 2 certificates (`openssl crl2pkcs7 -nocrl -certfile ca-bundle.crt | openssl pkcs7 -print_certs`).
- [Healthz poll before cert swap hits the old-cert API] → `validate_certs: no` makes it a pure liveness check; TLS trust is asserted later via kubectl with admin.conf.
- [`file state=touch` restart semantics differ from shell touch] → Verified equivalent for existing files (mtime update); both restart on every converge by design here.

## Migration Plan

Edit `defaults/main.yml` + `tasks/ipa-certs.yml`, write spec delta, run full converge then idempotence cycle (per role AGENTS.md tox commands). Expected: first converge changes the rewritten tasks; second converge reports them ok/no-change. Rollback = git restore of two files. Spec sync at archive time.

## Open Questions

None — all six review notes in `ipa-certs.yml` have a decided treatment (five nativized, one documented exception), and the wait convention was confirmed with the user.
