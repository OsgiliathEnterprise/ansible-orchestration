## Why

The "clean stale kubeadm state" block in `kube-install.yml` runs on every install, but its purpose is to clean residual state before re-init. It belongs in `delete-configuration.yml` where teardown logic lives, so it only runs when `reset_kube` is true.

## What Changes

- Move the 7-file cleanup block from `tasks/kube-install.yml:60-73` into `tasks/delete-configuration.yml` before the `kubeadm reset -f` task

## Capabilities

### Modified Capabilities
- `ipa-pki-bootstrap`: stale kubeadm cleanup moves to teardown phase

## Impact

- `tasks/kube-install.yml`: remove lines 60-73
- `tasks/delete-configuration.yml`: add cleanup block before `kubeadm reset`
