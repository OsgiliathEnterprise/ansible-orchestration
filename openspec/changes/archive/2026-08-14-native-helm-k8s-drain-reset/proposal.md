## Why

`drain-and-reset.yml` uses raw `ansible.builtin.command` for Helm and kubectl operations. This loses structured idempotency, proper change detection, and error handling provided by the `kubernetes.core` collection (already installed).

## What Changes

- Replace 4x `helm delete` commands with `kubernetes.core.helm` module
- Replace `kubectl drain` command with `kubernetes.core.k8s_drain` module
- Replace `kubectl delete node --all` command with `kubernetes.core.k8s` module (state=absent)
- Keep `kubeadm reset -f` as `ansible.builtin.command` (no native equivalent exists)

## Capabilities

### New Capabilities

(None — pure refactor)

### Modified Capabilities

(None — no spec-level behavior changes)

## Impact

- `tasks/drain-and-reset.yml` — 6 of 7 tasks rewritten
- No new dependencies required (`kubernetes.core` already installed)
