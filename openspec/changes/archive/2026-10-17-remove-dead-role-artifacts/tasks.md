## 1. Dead-code removal

- [x] 1.1 Delete the six `files/` manifests: `cluster-administrators-crb.yml`, `clusteradministrators.yml`, `namespace-creator-cr.yml`, `namespace-creator-crb.yml`, `namespace-requestor-crb.yml`, `namespace-requestors-cr.yml`
- [x] 1.2 Delete the two orphaned templates: `templates/bootstrap-kubelet.conf.j2`, `templates/discovery-kubeconfig.j2`
- [x] 1.3 Remove `kubernetes_node_cert_ttl_days: 365` (line 44) from `defaults/main.yml`
- [x] 1.4 Delete the two commented-out task blocks in `tasks/ipa-api-server.yml` (the `kinit` + `ipa cert-find` check at L8-16 and the `ipagroup` grant at L82-90, each with its trailing blank line); keep the live comment block at L32-45 and all live tasks
- [x] 1.5 Verify `git status` shows only the intended deletions/edits (plus this change's openspec artifacts)

## 2. Post-edit checks

- [x] 2.1 `git grep` each removed name (`cluster-administrators-crb`, `clusteradministrators`, `namespace-creator-cr`, `namespace-creator-crb`, `namespace-requestor-crb`, `namespace-requestors-cr`, `bootstrap-kubelet.conf.j2`, `discovery-kubeconfig.j2`, `kubernetes_node_cert_ttl_days`) returns no hits
- [x] 2.2 Confirm `ipa_group_kubeadm_exists` is still registered (`tasks/ipa-kubernetes-ca.yml:74`) and consumed (`tasks/ipa-kubernetes-ca.yml:88`), and `ipa_server_cert_valid` appears nowhere
- [x] 2.3 Run lint (`tox -e lint`)

    Evidence (2026-10-17, re-run to confirm): `tox -e lint` OK in 38.13s — yamllint and flake8 clean (no output), ansible-lint `Passed: 0 failure(s), 0 warning(s) in 83 files processed of 249 encountered`, profile `production`.

## 3. Verification

- [x] 3.1 `tox -e destroy -- --scenario-name=parallels`
- [x] 3.2 `tox -e converge-monorepo -- --scenario-name=parallels` succeeds with no reference errors to any deleted artifact
- [x] 3.3 `tox -e verify-monorepo -- --scenario-name=parallels` passes

    Evidence: converge `PLAY RECAP` master ok=352/changed=162/failed=0, node1 ok=162/changed=65/failed=0, node2 ok=162/changed=64/failed=0 (converge-monorepo: OK, ~1720s). Verify: 66 passed in 35.47s (verify-monorepo: OK). Lint (yamllint + flake8 + ansible-lint) green: 0 failure(s), 0 warning(s) in 81 files, profile `production`.

## 4. Docs + archive

- [x] 4.1 Run the `update-platform-docs` skill so the auto-generated variable table no longer lists `kubernetes_node_cert_ttl_days`

    Evidence (2026-10-17): diff-driven run — `scan-sources.sh` re-extracted `defaults/main.yml`; block `variables-tcharl-ansible-orchestration` in `src/site/asciidoc/admin/reference-variables.adoc` regenerated (removed `kube_credential_organization_name`, `kube_credential_cn`, `kubernetes_api_host` — no longer in defaults; added 11 newer defaults incl. `kube_credential_key_bits`, `ipa_kubeclusteradm_ca_name`, `orchestration_readiness_*`, `kubernetes_rollout_wait_timeout`; `kubernetes_node_cert_ttl_days` confirmed absent from the table). Gates: marker balance 23/23, personal-details scan clean, link sanity clean, `./mvnw site` exit 0. Report-only: deleted `files/*`/`templates/*` artifacts have no doc-prose references; `tasks/ipa-api-server.yml` change is a comment-only deletion (no behavior change). Observation: regenerated table now lists the `vault_kube_admin_password` default — the scan contract has no redaction; consider a redaction policy.
- [x] 4.2 Archive this change to `openspec/changes/archive/2026-10-17-remove-dead-role-artifacts/` (archived 2026-10-17; no `specs/` deltas to resync — pure cleanup change)
