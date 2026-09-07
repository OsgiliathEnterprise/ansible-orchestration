## Why

`tasks/ipa-certs-reapply.yml` contains only a port-6443 wait on masters, but its name, the `main.yml:60` task name ("Re-apply ConfigMap with IPA CA"), and the spec requirement *"ConfigMap is re-applied after API server stabilization"* all promise a ConfigMap re-application that **no task implements**. The file is a leftover from the superseded token+CA-hash join design — the current join (`kube-install-join-node.yml`) copies `admin.conf` directly and never reads the cluster-info ConfigMap. Its port wait duplicates `ipa-pki-swap.yml:85-91`.

## What Changes

- **Delete** `tasks/ipa-certs-reapply.yml` (20 lines).
- **Remove** its include block from `tasks/main.yml:60-63`.
- **Update** the comment at `tasks/kube-install.yml:74-78`, which lists `ipa-certs-reapply` as part of master post-processing.
- **Spec delta** on `ipa-pki-bootstrap`: remove the obsolete *"ConfigMap is re-applied after API server stabilization"* requirement (its final scenario line even describes the dead join-command reconstruction), and add a replacement requirement *"API server serves traffic after PKI swap"* that matches what `ipa-pki-swap.yml` actually does (port 6443 reachable + controller-manager Ready) so spec coverage of post-swap readiness is not silently lost.

## Capabilities

### New Capabilities

(None.)

### Modified Capabilities

- `ipa-pki-bootstrap`: remove the obsolete ConfigMap re-application requirement; add an API-server-readiness-after-swap requirement reflecting actual behavior in `ipa-pki-swap.yml`.

## Impact

- `tasks/ipa-certs-reapply.yml` — removed.
- `tasks/main.yml` — include block removed (also fixes the dangling-include breakage left by a previously staged deletion).
- `tasks/kube-install.yml` — comment-only edit (applies on top of change `remove-dead-join-code`, which extends the same comment block; implement that change first).
- `openspec/specs/ipa-pki-bootstrap/spec.md` — one requirement removed, one added.
- No converge behavior change: the deleted wait is redundant with `ipa-pki-swap.yml`.
