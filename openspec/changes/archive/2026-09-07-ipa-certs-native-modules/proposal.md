## Why

`tasks/ipa-certs.yml` mixes native modules with shell tasks that have direct native equivalents: `cat` to build the CA bundle (`changed_when: true`, never idempotent), three `sed -i` calls on the controller-manager manifest, a guarded `sed` on the scheduler manifest, a `touch` for the static-pod restart trigger, and two duplicate best-effort `kubectl cluster-info` tasks. The port-based `wait_for` also sleeps a fixed 10s before polling a raw port rather than confirming the API actually serves. These were flagged in review (L45 cat, L67 sed, L93 wait, L134 touch, L151 crypto module, L160 debug==verify).

## What Changes

All within `tasks/ipa-certs.yml` plus new variables in `defaults/main.yml`:

- **CA bundle build (L44-49)**: replace the `cat a b > c` shell with two `slurp` tasks + one `copy content=` — idempotent for free, no more unconditional `changed_when: true`.
- **Controller-manager manifest patching (L66-74)**: replace the three `sed -i` calls with three `ansible.builtin.replace` tasks (matching the style already used at L59-64 for the apiserver manifest).
- **Scheduler manifest patching (L76-84)**: replace the grep-guarded `sed` with a single unguarded `replace` — no-match reports ok, not failure, so the guard is unnecessary.
- **Readiness waits (L86-92, L139-148)**: replace the port-based `wait_for` and variabilize both healthz polls using new defaults (`kubernetes_api_host`, `kubernetes_api_port`, `kubernetes_api_ready_retries`, `kubernetes_api_ready_delay`) — tight polling of a real readiness endpoint instead of fixed-delay raw-port waits.
- **Static-pod restart trigger (L133-137)**: replace the `touch` shell with `ansible.builtin.file state=touch`.
- **Duplicate kubectl tasks (L160-180)**: consolidate the two identical best-effort `kubectl cluster-info` invocations into one retried task plus a single debug print.
- **openssl verify (L150-158)**: keep as shell but add an exception comment — no native chain-validation module exists in community.crypto 3.3.0 (`x509_certificate_info` parses fields only).
- **Spec delta** on `ipa-pki-bootstrap`: correct the stale *"Controller-manager and scheduler configs trust IPA CA"* scenario, which claims configs reference `ca.crt` while the code actually patches `--client-ca-file`/`--root-ca-file` to `ca-bundle.crt` and `--cluster-signing-cert-file` to `ca.crt.kubeadm` (the dual-CA design).

The review question "why rename to ca bundle?" (L81) is answered by documentation in change `agents-md-practices-c4` (dual-CA PKI trust diagram), not a code change.

## Capabilities

### New Capabilities

(None.)

### Modified Capabilities

- `ipa-pki-bootstrap`: the *"Controller-manager and scheduler configs trust IPA CA"* requirement's scenario text is corrected to match actual dual-CA patching behavior (no behavioral change — the delta fixes stale spec wording surfaced by this refactor).

## Impact

- `tasks/ipa-certs.yml` — six task rewrites, one comment addition.
- `defaults/main.yml` — four new variables with safe defaults (`127.0.0.1`, `6443`, `12`, `10`).
- No change to what gets patched or where; converge behavior is preserved (same substitutions, same restart trigger, same readiness semantics).
