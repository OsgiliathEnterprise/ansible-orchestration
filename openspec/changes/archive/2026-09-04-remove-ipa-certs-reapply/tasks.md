## 1. Code removal

- [x] 1.1 Delete `tasks/ipa-certs-reapply.yml`; verify `grep -rn "ipa-certs-reapply" tasks/ molecule/` returns no matches
- [x] 1.2 Remove the include block at `tasks/main.yml:60-63`; verify YAML parses and the surrounding includes (`kube-firewall`, `admin-user`) remain intact

## 2. Comment update

- [x] 2.1 Update the comment block at `tasks/kube-install.yml:74-78` to drop `ipa-certs-reapply` from the master post-processing list (applies on top of change `remove-dead-join-code`, which extends this same block — implement that change first); verify the comment reads coherently and no task lines were altered

## 3. Spec delta

- [x] 3.1 Verify the delta spec at `specs/ipa-pki-bootstrap/spec.md` (REMOVED ConfigMap requirement + ADDED readiness requirement) passes `openspec validate remove-ipa-certs-reapply`

## 4. Verification

- [x] 4.1 Run full converge (`tox -e converge-monorepo --scenario-name=parallels`) and confirm success with no dangling-include errors
- [x] 4.2 Run the idempotence check (second converge) and confirm zero changed tasks attributable to this change — expected output is identical since the deleted wait was redundant

    Evidence: run 7 (full converge, `converge-monorepo: OK`, failed=0 both hosts, zero refs to `ipa-certs-reapply` in log) followed by run 8 (second converge, `OK`, ~6.3 min). Task-level diff of run 8 vs pre-change baseline (run 6, IPs normalized): the only removed entries are the deleted wait task (`Ipa-certs-reapply | wait...` on master) and its include-skip on node1 — exactly this change's footprint. Three node1 status flips (conntrack sysctl, 2× Delete-configuration ok→changed) are VM-recreation variance between runs (VMs were rebuilt: idm .158→.163, master .145→.164), not attributable to this master-only diff.
