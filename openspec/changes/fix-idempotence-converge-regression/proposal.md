# Fix idempotence converge regression

## Why

The steady-state idempotence refactor moved the `/etc/containerd/config.toml` write out of `snippet_containerd.yml` (which had the writer and its handler flush together) into `tasks/fix-requirements.yml`, and the flush did not come along: `grep -rn flush_handlers tasks/` shows the role has none. On a fresh install the derived v4 config is deployed and notifies the `containerd` handler, but no flush runs before `kubeadm init`, so the daemon keeps serving the stale pre-deploy config and kubeadm dies with `[ERROR CRI]: unknown service runtime.v1.RuntimeService` (reproduced 2026-11-27, parallels scenario: master `failed=1` at kubeadm init, `kubernetesNodes` profile never created, both workers time out at the profile gate — exit 2).

## What Changes

- Restore the immediate restart guarantee for the single containerd config writer: after `Fix Requirements | Deploy containerd configuration` changes the file, the `containerd` refresh handler must be flushed before any later task in the play (cri facts, `kubeadm init`, join) can talk to the runtime.
- Correct the header comment of `tasks/fix-requirements.yml` to document the flush as load-bearing, so the invariant cannot silently regress again.
- No behavior change in steady state: when the deployed config already matches the derived content the copy reports `changed=false`, no handler is queued, and the flush is a no-op — the all-changed=0 converge proof is preserved.

## Capabilities

### New Capabilities
- `containerd-runtime-bootstrap`: the CRI runtime the kube bring-up tasks talk to is always the daemon running the role-deployed configuration — the config write and the daemon restart are atomic from the play's perspective, on fresh installs and at steady state.

### Modified Capabilities

<!-- No existing spec requirements change: kube-node-join's profile gate and structured diagnosis behaved exactly as specified (they correctly reported that the master never reached profile creation); steady-state-idempotence has no containerd requirements. -->

## Impact

- `tasks/fix-requirements.yml` (flush task + comment fix); role handlers unchanged.
- Unblocks the full parallels cycle (`destroy → converge-monorepo → verify-monorepo`) which is the standing gate for this role.
- Downstream symptoms removed: master kubeadm init CRI failure, missing `kubernetesNodes` profile, worker profile-gate 180-attempt timeouts in `tasks/kube-install-join-node.yml`.
