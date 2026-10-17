## 1. Task file split

- [x] 1.1 Create `tasks/ipa-controller-manager-client.yml` from the controller-manager half of `tasks/ipa-controlplane-clients.yml`: gate (read-only extraction of the embedded client-cert issuer from `/etc/kubernetes/controller-manager.conf` → `cm_swap_needed`), key, CSR, `ipacert` request, re-embed into `controller-manager.conf`, KCM static-pod restart; task-name prefix `Ipa-controller-manager-client`; header comment explaining the static-subject profile / host-principal constraint and the read-only shell exception
- [x] 1.2 Create `tasks/ipa-scheduler-client.yml` from the scheduler half: gate (same extraction from `/etc/kubernetes/scheduler.conf` → `scheduler_swap_needed`, temp file `/tmp/scheduler-current.crt`), key, CSR, `ipacert` request, re-embed into `scheduler.conf`, scheduler static-pod restart; task-name prefix `Ipa-scheduler-client`
- [x] 1.3 Update `tasks/ipa-certs.yml`: replace the single `include_tasks: ipa-controlplane-clients.yml` with two includes (controller-manager first, then scheduler), names updated
- [x] 1.4 Delete `tasks/ipa-controlplane-clients.yml`

## 2. Post-edit checks

- [x] 2.1 `git grep ipa-controlplane-clients` returns no hits (only historical openspec artifacts)
- [x] 2.2 `git grep cm_swap_needed` returns hits only in `tasks/ipa-controller-manager-client.yml`; `git grep scheduler_swap_needed` only in `tasks/ipa-scheduler-client.yml`
- [x] 2.3 Run lint (`tox -e lint`)

    Evidence: yamllint + flake8 + ansible-lint green (0 failure(s), 0 warning(s)), profile `production`.

## 3. Verification

- [x] 3.1 `tox -e destroy -- --scenario-name=parallels`
- [x] 3.2 `tox -e converge-monorepo -- --scenario-name=parallels` succeeds with no reference errors
- [x] 3.3 `tox -e verify-monorepo -- --scenario-name=parallels` passes

    Evidence: destroy OK. Converge `PLAY RECAP` master ok=355/changed=162/failed=0, node1 ok=162/changed=65/failed=0, node2 ok=162/changed=64/failed=0 (converge-monorepo: OK, 1653.18s). On-VM state (master): `controller-manager.conf` client cert issuer `O=OSGILIATH.TEST, CN=kubeclusteradm`, subject `O=system:masters, CN=system:kube-controller-manager`; `scheduler.conf` client cert issuer `CN=kubeclusteradm`, subject `O=system:masters, CN=system:kube-scheduler`; scheduler pod Ready; `controller-manager-client.{crt,csr,key}` and `scheduler-client.{crt,csr,key}` all present in `/etc/kubernetes/pki/`. Verify: 66 passed in 34.51s (verify-monorepo: OK).

## 4. Docs + archive

- [x] 4.1 Update the role `AGENTS.md` L3 task-flow graph (`ipa-controlplane-clients.yml` → `ipa-controller-manager-client.yml` + `ipa-scheduler-client.yml`)
- [x] 4.2 Run the `update-platform-docs` skill

    Evidence (diff-driven run): changed paths = `tasks/ipa-certs.yml` (M), `tasks/ipa-controller-manager-client.yml` (A), `tasks/ipa-scheduler-client.yml` (A), `tasks/ipa-controlplane-clients.yml` (D), role `AGENTS.md` (M). Classification per `sources-of-truth.md`: task-file changes → report-only (no doc page references the split task files; role variable table in `admin/reference-variables.adoc` untouched — `defaults/` unchanged); role `AGENTS.md` → unmapped (not platform documentation). No pages updated, no blocks regenerated, no prose rewritten. Gates: `./mvnw site` exit 0; marker balance / personal-detail / link gates trivially satisfied (no pages touched).
- [x] 4.3 Archive this change to `openspec/changes/archive/`

    Evidence: delta spec synced into `openspec/specs/ipa-pki-bootstrap/spec.md` (requirement extended with the independent-gating clause + 3 scenarios; diff verified: only that requirement section changed), then moved to `openspec/changes/archive/2026-10-17-decouple-controlplane-client-certs/` (`.openspec.yaml` preserved). `openspec list` shows the change no longer active.
