## 1. Implement password activation in ipa-kube-admin-credential.yml

- [x] 1.1 Add "activate kubeclusteradm password if KDC reports it expired" task between user creation and kinit verification: plain one-line `kinit` first; on failure retry with three lines of stdin (old + new + confirm, same value) driving the forced-change flow; `|| exit 1` guard so a failed second attempt cannot be masked
- [x] 1.2 Set `changed_when: "'activated' in stdout"` on the activation task and keep `no_log: "{{ secure_logs }}"` consistent with sibling tasks
- [x] 1.3 Update the file header comment to document FreeIPA's immediately-expired API-set password behavior

## 2. Verify

- [ ] 2.1 Run lint gate (`tox -e lint`) in the role directory
- [ ] 2.2 Full molecule cycle on `parallels`: destroy → converge-monorepo (fresh VM must pass kinit verification without manual intervention) → verify-monorepo
- [ ] 2.3 Re-converge to confirm idempotent behavior: activation task reports ok (`already-active`), kinit verification and kubectl check still pass
