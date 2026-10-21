# Tasks

## 1. Scenario override

- [ ] 1.1 Add `kubernetes_rollout_wait_timeout: 600` to the play `vars:` block in `molecule/kvm/converge.yml`, with a comment naming the constrained single-worker CI topology (2GB/2vCPU VMs on an 8GB/2vCPU runner) and the calibration rule (keep the budget at ≥2× the measured calico wait `duration`, design D2). Verify: `yamllint molecule/kvm/converge.yml` passes and the var is present (`grep kubernetes_rollout_wait_timeout molecule/kvm/converge.yml`).
- [ ] 1.2 Confirm the override is scenario-local: `defaults/main.yml` is unchanged (role default stays 300) and no other scenario's converge play references the variable. Verify: `grep -rn kubernetes_rollout_wait_timeout molecule/` matches only `molecule/kvm/converge.yml`, and `git diff --stat` shows `molecule/kvm/converge.yml` (plus the docs from 1.3) as the only changed files.
- [ ] 1.3 Note the override in `AGENTS.md`'s KVM execution section (one line: the `kvm` scenario overrides `kubernetes_rollout_wait_timeout` in `molecule/kvm/converge.yml` for the constrained CI topology; the value is calibrated from the measured calico wait duration). Verify: the note's value matches the var in `molecule/kvm/converge.yml` and the file renders as valid Markdown.

## 2. Local gates and no-regression (macOS host)

- [ ] 2.1 Lint gate: `uv tool run --python 3.13 --with tox tox -e lint` exits 0 (yamllint + ansible-lint clean for the touched file). Verify: exit code 0.
- [ ] 2.2 No-regression proof that the default-300 path is untouched: full `parallels` cycle — `tox -e destroy -- --scenario-name=parallels`, then `tox -e converge-monorepo -- --scenario-name=parallels`, then `tox -e verify-monorepo -- --scenario-name=parallels` (wait for long-running tasks; on a prepare/converge failure, destroy and retry once). Verify: converge and verify are green, and the `Calico-ca-recovery | patch calico-node` task in the converge log reports a `duration` below 300 (role default in force for `parallels`).

## 3. Documentation impact check

- [ ] 3.1 Confirm auto-generated platform docs are unaffected: `defaults/main.yml` is unchanged, so the `reference-variables.adoc` variable table and repo-layout blocks must not change. Verify: run `/update-platform-docs` in diff-driven mode and confirm the regenerated blocks are unchanged (empty diff), or record an explicit no-impact note citing the unchanged scan source.

## Workflow follow-up

- After 3.1 is done: archive the change (`openspec archive kvm-calico-rollout-wait`), which merges the `kvm-scenario-topology` delta into `openspec/specs/kvm-scenario-topology/spec.md`.
