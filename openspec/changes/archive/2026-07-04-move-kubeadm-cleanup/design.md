## Context

The "clean stale kubeadm state" block at `kube-install.yml:60-73` removes 6 config files and `/etc/kubernetes/pki` on every install. This runs unconditionally, but its purpose is to clean residual state before re-init.

## Goals / Non-Goals

**Goals:**
- Move cleanup to `delete-configuration.yml` so it only runs during teardown

**Non-Goals:**
- Changing which files are cleaned

## Decisions

- Insert cleanup block before `kubeadm reset -f` in `delete-configuration.yml` — the reset command needs clean state to succeed

## Risks / Trade-offs

- On a fresh install without `reset_kube`, stale state won't be cleaned. But `kubeadm reset -f` and the existing `/etc/kubernetes` removal in `delete-configuration.yml` already handle this on first run.
