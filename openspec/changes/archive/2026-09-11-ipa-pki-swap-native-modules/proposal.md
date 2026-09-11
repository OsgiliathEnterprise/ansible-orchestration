## Why

`tasks/ipa-pki-swap.yml` carries the same review-flagged patterns as `ipa-certs.yml`: a shell loop of four `sed -i` calls on kubeconfigs (`changed_when: true`, never idempotent), two more `replace` tasks with incorrect `changed_when: true` overrides, three `touch` shells for static-pod restarts, two fixed-delay port-based `wait_for` sleeps, a manual `seq`/`sleep` polling loop for controller-manager readiness, and a Python patch script that unconditionally rewrites the kubelet config (`changed_when: true`) forcing a kubelet restart on every converge. It also contains a dead task: the user-kubeconfig sed patch (L24-33) — `/root/.kube/config` is a symlink to `admin.conf` (re-created with `force: true` ten lines later, so any effect is erased), and `/home/vagrant/.kube/config` does not exist on these VMs (nothing creates it; the `[ -f ]` guard always skips).

## What Changes

All within `tasks/ipa-pki-swap.yml`:

- **Kubeconfig CA patching (L3-12)**: replace the shell loop of four `sed -i` calls with one `ansible.builtin.replace` task looping over the four files (`controller-manager.conf`, `scheduler.conf`, `kubelet.conf`, `admin.conf`), preserving indentation via a capture group. Idempotent for free; drop `changed_when: true`.
- **Dead user-kubeconfig patch (L24-33)**: delete the task entirely — verified dead (see Why). The `/root/.kube/config → admin.conf` symlink task (L35-41) stays; testinfra tests run kubectl as root via `host.sudo()` and rely on it.
- **Server-URL replaces (L43-57)**: drop the incorrect `changed_when: true` overrides from the two existing `replace` tasks so re-runs report ok.
- **Static-pod restart triggers (L59-63, L73-83)**: replace three `touch` shells with `ansible.builtin.file state=touch`.
- **Readiness waits (L65-71, L85-91)**: replace both port-based `wait_for` tasks with `/healthz` `uri` polls using the variables introduced by change `ipa-certs-native-modules` (`kubernetes_api_host`, `kubernetes_api_port`, `kubernetes_api_ready_retries`, `kubernetes_api_ready_delay`).
- **Controller-manager readiness (L93-105)**: replace the manual `seq 1..12 / sleep 10` shell loop with a single kubectl command using native `retries`/`until` (same pattern already used at L143-151). Shell kept as a documented exception — no native module accepts an arbitrary kubeconfig path.
- **Kubelet API override patch (L107-141)**: make the Python script idempotent — it prints `CHANGED`/`UNCHANGED`, writes only when values differ; the task uses `changed_when: "'CHANGED' in result.stdout"` and the kubelet restart becomes conditional on that, dropping both `changed_when: true` overrides.

## Capabilities

### New Capabilities

(None.)

### Modified Capabilities

(None — all specced behavior is preserved: configs patched to trust the IPA CA, static pods restarted, controller-manager readiness verified. The changes alter *how* (module choice, idempotency), not *what*.)

## Impact

- `tasks/ipa-pki-swap.yml` — one task deleted, six tasks rewritten, two `changed_when` overrides removed.
- Depends on change `ipa-certs-native-modules` for the four new defaults variables (implement that change first).
- Converge behavior preserved; idempotence improves: a second converge no longer re-patches kubeconfigs, re-touches manifests, or restarts kubelet when nothing changed.
