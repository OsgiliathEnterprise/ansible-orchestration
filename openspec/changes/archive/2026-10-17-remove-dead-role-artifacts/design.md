## Context

See proposal.md for motivation. Verified facts shaping this change:

- Every one of the eight deleted files is referenced by no `include_tasks`, `import_tasks`, `template:`, `copy: src:`, `lookup('file', ...)`, or `kubectl apply -f` anywhere in `tasks/`, `templates/`, `molecule/`, `defaults/`, `vars/`, or `meta/` (grep on each file base name), and `git grep` across the whole repo finds no reference outside the files' own contents.
- `git log` history: the six `files/` manifests were last used before `d8993fa` (node join gated on the validated IPA kubernetesNodes profile); both templates were orphaned at `0a5c4b5` (FreeIPA cert issuance replacing manual bootstrap/discovery kubeconfig generation).
- `kubernetes_node_cert_ttl_days` has zero occurrences outside its own definition line in `defaults/main.yml:44` (checked `tasks/`, `molecule/`, `templates/`, `defaults/`, `vars/`, `openspec/`).
- The two commented-out blocks in `tasks/ipa-api-server.yml` are the only commented-out task syntax in the role (grep for `# - name:` / commented module keys across `tasks/`). Their apparent register targets (`ipa_server_cert_valid`) have zero live consumers; `ipa_group_kubeadm_exists`, referenced by the second block's `when`, is registered at `tasks/ipa-kubernetes-ca.yml:74` and consumed at `tasks/ipa-kubernetes-ca.yml:88` by *live* tasks — so only the comment block is dead, the variable is not.
- `pyproject.toml` sdist target lists whole directories (`/files`, `/templates`), so deleting members needs no packaging change.

## Goals / Non-Goals

**Goals:**
- Remove all nine dead artifacts (six `files/`, two `templates/`, one default variable, two commented-out blocks) in one audited change.
- Keep the live comment block at `tasks/ipa-api-server.yml:32-45` (it explains the active `ipacert` task's `skip_host_check`/`force` choices).

**Non-Goals:**
- No spec deltas — no requirement references any deleted artifact.
- No changes to `requirements-monorepo.yml`, `requirements-standalone.yml` (dead role entries there are a separate, follow-up change).
- No changes to `roles/AGENTS.md` (the stale "four orphaned task files" note is a separate documentation fix).
- No touching `files/calico.conf` or the four live templates.

## Decisions

**D1: Delete the six `files/` manifests outright.**
They encode the abandoned RBAC bootstrap (cluster-admin CRB, namespace creator/requestor CRs). No live code path can reach them (Ansible files under `files/` are only reachable via `src:`/`lookup`/explicit paths, all checked). The modern equivalents (cluster-admin credential from the `kubeclusteradm` CA, namespace RBAC) live in `tasks/admin-user.yml` + `tasks/ipa-kube-admin-credential.yml` and do not use these manifests.
*Alternative considered:* keep as reference — rejected, the no-dead-code rule makes unreferenced artifacts review findings, and git history preserves the content.

**D2: Delete both orphaned templates.**
`bootstrap-kubelet.conf.j2` and `discovery-kubeconfig.j2` predate IPA-issued kubelet/client certs; the system-path references to `bootstrap-kubelet.conf` in `kube-install-join-node.yml` and `kube-apiserver-kubelet-client.yml` point at files produced by `kubeadm init`/`kubeadm join`, not rendered from these templates.
*Alternative considered:* re-wire one of them — rejected; the node join flow was deliberately reworked (change `2026-09-24-decouple-node-join-from-master`) around file-based discovery with IPA-signed certs.

**D3: Remove `kubernetes_node_cert_ttl_days` from defaults.**
Zero consumers role-wide. Node cert TTL is not currently parameterized; if it ever becomes real, the variable returns with consumers in the same change.
*Alternative considered:* wire it into the `kube-cert-renew` timer — rejected, that is feature work, not cleanup; the variable must not exist unused.

**D4: Delete only the two commented-out task blocks in `ipa-api-server.yml`, keep surrounding live comments.**
The `kinit`+`ipa cert-find` block and the `ipagroup` block are fully commented (no live line inside), and their registers/consumers are gone. The L32-45 comment block is load-bearing documentation for the active `ipacert` task and stays.
*Alternative considered:* delete the whole `ipagroup` idea including `ipa_group_kubeadm_exists` — rejected, that variable is live in `ipa-kubernetes-ca.yml`.

## Risks / Trade-offs

- [A hidden consumer (e.g., a playbook outside the role, or a docs page) references a deleted name] → Mitigation: `git grep` across the whole repo before deletion (done: only the artifacts themselves match); platform docs regenerated in the same change (variable table is auto-generated between markers, so it cannot retain a stale entry after regeneration).
- [Deleting the default variable shifts a value used implicitly] → Mitigation: verified zero references before deletion; Ansible defaults with no consumers are inert by definition.
- [Converge behavior unexpectedly changes] → Mitigation: full destroy → converge-monorepo → verify-monorepo cycle on the `parallels` scenario after deletion; expected result is identical task output since no artifact was in an execution path.

## Migration Plan

Apply deletions, run the full molecule cycle (per role AGENTS.md tox commands), regenerate platform docs, archive this change. Rollback = `git restore` of the nine artifacts. No data migration.

## Open Questions

None — every artifact's dead status was established by reference greps plus git history before this change was proposed.
