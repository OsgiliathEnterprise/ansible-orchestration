## Context

See proposal.md for motivation. Verified facts shaping this change:

- `tcharl.kubernetes/tasks/control-plane-setup.yml` creates `/root/.kube/config` as a symlink to `admin.conf`; nothing in the role or scenario creates `/home/vagrant/.kube/config`.
- Testinfra tests (`molecule/default/tests/test_master.py`) connect as vagrant but run kubectl via `host.sudo()` — i.e. as root, reading `/root/.kube/config` (the symlink). This is why the L35-41 symlink task exists and must stay.
- The user-kubeconfig sed task (L24-33) therefore patches a file whose effect is erased ten lines later (`file state=link force: true`) and a file that does not exist — dead on both branches of its `[ -f ]` guard.
- `ipa-pki-swap.yml` runs on the master with `become`, so polling `127.0.0.1` is equivalent to the current `orchestration_master_ip` in L85-91.

## Goals / Non-Goals

**Goals:**
- Nativize every shell task in `ipa-pki-swap.yml` that has a native equivalent; delete the dead user-kubeconfig patch.
- Make the kubelet override patch idempotent so re-converges stop restarting kubelet unconditionally.
- Reuse change `ipa-certs-native-modules`' readiness variables for consistent, variable-driven waits.

**Non-Goals:**
- No change to what gets patched (CA path, server URL, apiServerOverride values) or the restart order of static pods.
- No spec delta — all specced behavior is preserved (see proposal).

## Decisions

**D1: Kubeconfig CA patching via one `replace` task with a loop.**
`regexp: '^(\s*)certificate-authority-data:.*'`, `replace: '\1certificate-authority: /etc/kubernetes/pki/ca.crt'` (single-quoted YAML so the backreference stays literal; Ansible's replace uses Python re.sub semantics). Loop over the four files. No-match reports ok, so the task is idempotent without `changed_when`.
*Alternative considered:* keep per-file shell seds — rejected; same flagged pattern as change 4.

**D2: Delete the user-kubeconfig patch task (L24-33).**
Both targets are dead: `/root/.kube/config` is a symlink whose patched state is erased by the force re-symlink at L35-41, and `/home/vagrant/.kube/config` does not exist on these VMs. The symlink task itself stays — testinfra's root-context kubectl calls depend on it.
*Alternative considered:* keep with stat guards — rejected; preserving a no-op task violates the no-dead-code rule.

**D3: Drop `changed_when: true` from the two server-URL `replace` tasks.**
The module already reports change correctly; the override masks idempotence (re-runs report changed).

**D4: Three `touch` shells → `file state=touch`.**
Same semantics as change 4 D4 (mtime update triggers kubelet static-pod restart); both versions restart on every converge — preserved, not fixed here.

**D5: Both port-based `wait_for` tasks become `/healthz` polls with shared variables.**
Uses `kubernetes_api_host/port/ready_retries/ready_delay` from change 4's defaults (implement that change first). L85-91 currently targets `orchestration_master_ip`; since the task runs on the master, `127.0.0.1` is equivalent and unifies both files under one convention.
*Alternative considered:* keep `wait_for` with variables — rejected (listening port ≠ serving API).

**D6: Controller-manager readiness via native `retries`/`until`.**
One kubectl command registered, `retries: 12`, `delay: 10`, `until: "'True' in cm_ready.stdout"` — identical timing to the current loop (12 × 10s), no manual `seq`/`sleep`. Shell kept as a documented exception: no native module accepts an arbitrary kubeconfig path, and this matches the file's existing L143-151 pattern.

**D7: Idempotent kubelet override patch + conditional restart.**
The copied Python script compares desired vs current `apiServerOverride` values and prints `CHANGED`/`UNCHANGED`, writing only on difference (also drops its unused `import os`). The task registers output with `changed_when: "'CHANGED' in result.stdout"`; the kubelet `service restarted` task gains `when: <patch> is changed` and loses `changed_when: true`.
*Alternative considered:* native YAML editing — no Ansible module sets nested keys in an existing YAML file without full-file templating, which would risk reformatting unrelated content; the script approach with a change marker is the standard pattern.

## Risks / Trade-offs

- [Backreference handling differs from sed] → Verified: Ansible replace passes the replacement string to `re.sub`, so `\1` works; YAML single quotes keep it literal. Converge verification checks the patched lines retain their original indentation.
- [Deleting L24-33 breaks an unseen consumer of `/home/vagrant/.kube/config`] → Mitigation: grep across role, scenario, and tests shows no writer or reader (tests use root context); if a future scenario adds that file, the patch returns with it.
- [`sed -i` on the `/root/.kube/config` symlink was actually replacing the symlink with a regular file mid-run] → No lasting effect: L35-41 force-recreates the symlink before any test runs; nothing reads the intermediate state (verified by task order in `main.yml`).
- [Healthz poll sees the old-cert API during restart] → `validate_certs: no` makes it a liveness check; TLS trust is asserted later by the kubectl cluster-info verification.
- [Conditional kubelet restart skips a needed restart] → The patch task is the only writer of `apiServerOverride`; if it reports unchanged, nothing needs re-applying.

## Migration Plan

Implement after change `ipa-certs-native-modules` (needs its defaults variables). Edit `tasks/ipa-pki-swap.yml`, run full converge then idempotence cycle. Expected: first converge changes the rewritten tasks; second converge reports them ok/no-change and does not restart kubelet. Rollback = git restore of one file.

## Open Questions

None — the dead-code determination for L24-33 was verified against `tcharl.kubernetes` (kubeconfig creation) and the test suite (root-context kubectl), and the wait convention follows the user's confirmed decision from change 4.
