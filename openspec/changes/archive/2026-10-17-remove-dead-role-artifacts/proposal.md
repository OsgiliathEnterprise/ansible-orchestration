## Why

A dead-code audit of this role found nine artifacts with zero consumers:

- Six Kubernetes RBAC/namespace manifests under `files/` (`cluster-administrators-crb.yml`, `clusteradministrators.yml`, `namespace-creator-cr.yml`, `namespace-creator-crb.yml`, `namespace-requestor-crb.yml`, `namespace-requestors-cr.yml`). They were used by an early cluster-admin bootstrap design and were orphaned when node join / admin credential moved to IPA-issued certificates (last real use predates commit `d8993fa`). `git grep` across the whole repo confirms no task, template, or molecule file references them.
- Two templates (`bootstrap-kubelet.conf.j2`, `discovery-kubeconfig.j2`) orphaned at `0a5c4b5` ("use freeipa to emit kube certificates"): node bootstrap and discovery kubeconfigs are now produced by `kubeadm`/IPA, not by this role. The only `bootstrap-kubelet.conf` hits in `tasks/` are the *system path* `/etc/kubernetes/bootstrap-kubelet.conf` (kube-install-join-node.yml:192, kube-apiserver-kubelet-client.yml:121), not the template.
- One default variable, `kubernetes_node_cert_ttl_days` (`defaults/main.yml:44`), defined but referenced nowhere — not in tasks, molecule, templates, or `openspec/`.
- Two commented-out task blocks in `tasks/ipa-api-server.yml`: a `kinit` + `ipa cert-find` validity check (L8-16, whose `register: ipa_server_cert_valid` is commented out and consumed by nothing) and an `ipagroup` grant for `kubernetes-administrators` (L82-90). The `ipa_group_kubeadm_exists` variable referenced by the second block stays alive: it is registered and consumed in `tasks/ipa-kubernetes-ca.yml` (L74, L88) by live tasks.

Per the monorepo no-dead-code rule (`roles/AGENTS.md`), orphaned artifacts are review findings, not acceptable residue.

## What Changes

- **Delete** the six `files/` manifests listed above.
- **Delete** `templates/bootstrap-kubelet.conf.j2` and `templates/discovery-kubeconfig.j2`.
- **Delete** the `kubernetes_node_cert_ttl_days` line from `defaults/main.yml`.
- **Delete** the two commented-out task blocks in `tasks/ipa-api-server.yml` (L8-16 and L82-90, plus their trailing blank lines). The live explanatory comment block above the `ipacert` task (L32-45) is kept — it documents the active task.
- **Update** platform docs auto-generated variable table (via the `update-platform-docs` skill) so `kubernetes_node_cert_ttl_days` disappears from it.

## Capabilities

### New Capabilities

(None — pure dead-code removal.)

### Modified Capabilities

(None — no requirement references any deleted artifact; behavior is unchanged because nothing was in an execution path.)

## Impact

- `files/` — six manifests removed; `files/calico.conf` (used by `tasks/firewall.yml`) untouched.
- `templates/` — two templates removed; the four live templates (`calico_configuration.yml.j2`, `kube-cert-renew.{service,sh,timer}.j2`, `persistent-volume.yml.j2`) untouched.
- `defaults/main.yml` — one line removed; no task reads the variable.
- `tasks/ipa-api-server.yml` — comments only; no live task, variable, or `register` is altered.
- `pyproject.toml` sdist includes whole `/files` and `/templates` directories, so no packaging manifest update is needed.
- No converge/idempotence behavior change: every deleted artifact was outside all execution paths. Out of scope (tracked separately): dead entries in `requirements-monorepo.yml`/`requirements-standalone.yml` and the stale "four orphaned task files" note in `roles/AGENTS.md`.
