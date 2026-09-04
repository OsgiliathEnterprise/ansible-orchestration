## 1. Dead-code removal

- [x] 1.1 Confirm no references remain: `grep -rn "kube-install-refresh-join" tasks/ molecule/` returns nothing, and verify the file is not reachable via any include/import chain from `main.yml`
- [x] 1.2 Delete `tasks/kube-install-refresh-join.yml`; verify `git status` shows only that deletion (plus the comment edit in task 2.1)

## 2. Intent clarification

- [x] 2.1 Extend the comment block at `tasks/kube-install.yml:74-78` with one line stating `kubernetes_join_command` is set empty on purpose to disable the built-in node join (join handled by `kube-install-join-node.yml`); verify the rendered comment reads coherently and no task/variable lines were altered

## 3. Verification

- [x] 3.1 Run full converge (`tox -e converge-monorepo --scenario-name=parallels`) and confirm it succeeds with no reference errors to the deleted file
- [x] 3.2 Run idempotence check (second converge) and confirm zero changed tasks attributable to this change — expected output is identical to pre-change behavior since the file was never in an execution path

    Evidence: two consecutive converges on the healthy cluster (runs 5 & 6, both `converge-monorepo: OK`, failed=0). Identical PLAY RECAP profiles (master ok=261/changed=76/skipped=70; node1 ok=147/changed=35/skipped=59) — all changed tasks are the role's by-design `reset_kube: True` reset/recreate behavior, none attributable to this diff. Zero references to `kube-install-refresh-join` in either run log. The re-converge also exercised the section 4 fix (all four revoke tasks ran with flat `.serial_number`, no undefined errors).

## 4. Pre-existing bug fix (unblocks 3.2, approved by user)

- [x] 4.1 Fix `tasks/delete-ipa-cleanup.yml`: all four revoke tasks referenced `._cert_info.cert.serial_number`, but `community.crypto.x509_certificate_info` returns a flat dict (`serial_number` at top level). Only fires on re-converge (fresh converge skips the tasks because certs don't exist yet), which blocked the idempotence check. Changed to `._cert_info.serial_number` in 4 places.

## 5. Environment workarounds (VM-local, not part of this change's diff)

- [x] 5.1 node1 could not resolve `master.osgiliath.test`: systemd-resolved global scope (`/etc/systemd/resolved.conf.d/head.conf`, written by `tcharl.ansible_nameserver`) lists `DNS=10.211.55.158 8.8.8.8` for the `~osgiliath.test` routing domain; with outbound internet, resolved adopted Google's NXDOMAIN over idm's correct A record (verified: `dig @10.211.55.158 master.osgiliath.test` → 10.211.55.145, `dig @8.8.8.8` → NXDOMAIN). Workaround: appended static `/etc/hosts` entries on node1 (`master.osgiliath.test`) and master (`node1.osgiliath.test`). Proper fix belongs in `tcharl.ansible_nameserver` (separate change).
