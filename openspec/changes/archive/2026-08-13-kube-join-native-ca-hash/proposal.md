## Why

The task "Kube-install-refresh-join | get current CA DER hash from ConfigMap on master" uses `shell` + `curl` to fetch the Kubernetes API's cluster-info ConfigMap, then embeds Python code for parsing. This is fragile, hard to read, and bypasses Ansible's native HTTP capabilities.

## What Changes

- Replace `ansible.builtin.shell` with `curl -sk` by using `ansible.builtin.uri` (or `get_url`) to fetch the cluster-info ConfigMap from the Kubernetes API
- Replace inline Python parsing block with native Ansible modules (`ansible.builtin.slurp`, `ansible.builtin.set_fact`, etc.) for certificate extraction and hash computation
- Preserve identical behavior: same retry logic, same output variable, same delegation

## Capabilities

### New Capabilities

(None — pure refactor)

### Modified Capabilities

(None — no spec-level behavior changes; only implementation details change)

## Impact

- `tasks/kube-install-refresh-join.yml` — single task replacement
- No new dependencies required (`uri`/`get_url` are built-in Ansible modules)
- Behavior and output remain identical
