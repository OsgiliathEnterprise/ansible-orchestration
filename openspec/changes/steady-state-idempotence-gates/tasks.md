# Tasks

## 1. Threshold single-source and shared gate include

- [ ] 1.1 Add `kube_cert_renewal_threshold_days: 30` to `defaults/main.yml` with a comment tying it to the renewal timer, and verify with `ansible-lint` on the role plus the variable being referenceable in templates
- [ ] 1.2 Replace the hardcoded `-days 30` / `-checkend` values in `templates/kube-cert-renew.sh.j2` with `{{ kube_cert_renewal_threshold_days }}`, and verify by converging and reading `/usr/local/bin/kube-cert-renew.sh` on a kube host (`vagrant ssh <id> -c "sudo grep -n checkend /usr/local/bin/kube-cert-renew.sh"`) showing the templated value
- [ ] 1.3 Update the 30-day eligibility check in `tasks/certs/ipa-cert-renewal.yml` to use `kube_cert_renewal_threshold_days`, and verify converge stays green and the rendered comparison uses the default
- [ ] 1.4 Create `tasks/certs/_cert_swap_decision.yml`: parameterized include (`cert_path`, `expected_issuer_glob`, register prefix) performing the issuer check (`openssl x509 -issuer`, with the shell-exception comment), the leaf validity check (`not_after` vs `now() + kube_cert_renewal_threshold_days` via `community.crypto.x509_certificate_info`), and the CA validity check; registers `<prefix>_swap_needed` and `<prefix>_cert_info`, writes nothing, and verify with `ansible-lint` clean plus successful inclusion from task 2.1's caller

## 2. Truthful change reporting for IPA CA configuration (option A)

- [ ] 2.1 Extend `scripts/ipa-ca-ensure.sh` so `ca-set-service-category` echoes `SERVICECAT-SET` and `ca-add-profile` echoes `CA-PROFILE-ADDED` only when the write actually occurred (document the marker set in the script header), and verify by running the script twice on idm — first run prints markers, second run prints none — via `vagrant ssh <idm> -c "sudo <script> ..."`
- [ ] 2.2 In `tasks/certs/ipa-ca-ensure.yml`, replace blanket/missing `changed_when` on the service-category and profile steps with marker-derived `changed_when` (`'SERVICECAT-SET' in stdout`, `'CA-PROFILE-ADDED' in stdout`) alongside the existing `CA-ACL-ADDED`, and verify a reconverge on an already-converged cluster reports those tasks `ok`
- [ ] 2.3 Gate the `ipa ca` parameter sets (profile rules, `ca_enable`, delivery methods) behind a read-only `ipa ca-show kubernetes-ca` (delegated to idm through `tasks/_krb_ticket.yml`) and run each set only when a value differs, and verify a reconverge reports no change while forcing a wrong value on idm makes the next converge report changed and restore it
- [ ] 2.4 In `tasks/certs/ipa-cert-renewal.yml`, fix the CA ACL grant loop to evaluate per item (per-item result, not last-iteration `item.changed`; add via the loop only when the host is absent from the delegated `ca-show` host list) and verify a steady-state reconverge reports the loop `ok` for every host
- [ ] 2.5 Gate `kubeclusteradm` keytab generation/export behind the existing `_probe-kubeclusteradm-keytab.yml` usability probe (regenerate only when the probe fails or the keytab file is missing; keep the delete-before-`ktadd` and 0600 lockdown), and verify a reconverge reports the keytab tasks `ok` while deleting the keytab on idm makes the next converge report changed and restore it

## 3. Certificate issuance and manifest-swap gates

- [ ] 3.1 In `tasks/certs/ipa-controller-manager-client.yml`, replace the inline issuer check with `tasks/certs/_cert_swap_decision.yml` (adds validity + CA gates), and split the static-pod manifest move into its own gate: move only when the manifest's `client-certificate-data` differs from the current crt (or the manifest is missing — repair path), and verify a reconverge performs no issuance and no `mv` (task list shows `ok`, not `changed`, and file mtime of the static pod manifest is unchanged)
- [ ] 3.2 Apply the same shared-gate include and split manifest-move gate to `tasks/certs/ipa-scheduler-client.yml`, and verify the same reconverge no-op evidence as 3.1
- [ ] 3.3 In `tasks/admin-user.yml`, gate the `admin.conf` client-cert re-embed on content equality: `slurp` `/var/lib/kube-clusteradm.crt` and compare its base64 against the `client-certificate-data` currently embedded in `admin.conf`; re-embed only on mismatch or missing block, and verify a reconverge reports the re-embed task `ok` while blanking the block by hand on master makes the next converge report changed and restore it (keeping the existing `kubectl get nodes` verification green afterward)

## 4. PKI bundle swap idempotence

- [ ] 4.1 In `tasks/certs/ipa-pki-swap.yml`, build the 2-CA bundle in memory (`slurp` both CA files) and write `/etc/kubernetes/pki/ca-bundle.crt` with `copy: content:` (content-idempotent), removing the separate CA-changed shell gate and any blanket `changed_when`, and verify a steady-state reconverge reports the bundle task `ok` and a rotated CA still flips it to `changed`
- [ ] 4.2 Gate the kubeconfig/static-pod manifest moves in `tasks/certs/ipa-pki-swap.yml` on the bundle copy reporting changed **or** a per-manifest end-state check (`slurp` + compare against the rendered bundle fingerprint — restores externally deleted or mutated manifests), keeping the `openssl verify` chain check and the KCM-lease/scheduler-Ready/`kubectl` gates unconditional, and verify a steady-state reconverge reports the moves `ok`, while deleting a manifest copy on master makes the next converge restore it and report changed

## 5. PersistentVolume apply idempotence

- [ ] 5.1 In `tasks/persistent-volume.yml`, add a read-only `kubernetes.core.k8s_info` lookup (delegate_to master, admin kubeconfig) and skip both the `state: absent` and the apply when the named PV exists with matching `spec.nfs.server`, `spec.nfs.path`, capacity, accessModes, and storageClassName; delete+apply on drift; and remove `failed_when: false` from the apply, and verify a steady-state reconverge reports the PV tasks `ok` (PV UID unchanged — `vagrant ssh <master> -c "sudo kubectl get pv -o jsonpath='{.items[*].metadata.uid}'"` before/after), while changing `subtree` in the mountpoint config triggers delete+recreate on the next converge

## 6. Integration verification (full molecule cycle)

- [ ] 6.1 Run the host-OS-matched full cycle (`destroy → converge-monorepo → verify-monorepo` with `--scenario-name=parallels` on macOS) and verify the first converge succeeds with all verify gates green (nodes Ready, per-pod evidence, PV mounts)
- [ ] 6.2 Reconverge on the converged cluster and capture the task-change report: verify the run is near-zero-change — only the `kubectl get nodes` verification task may report changed, and no cert issuance, manifest move, bundle rewrite, PV recreate, ACL grant, or keytab export reports changed — then re-run `verify-monorepo` and confirm it stays green
- [ ] 6.3 Replay test: on the converged cluster, force a gate replay (expire-or-pretend by temporarily lowering `kube_cert_renewal_threshold_days` via `-e`, e.g. `-e kube_cert_renewal_threshold_days=3650`, on the converge) and verify the cert gates flip to `changed` and re-issue, then converge once more without the override and verify the cluster returns to the steady-state zero-change report

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied (diff review of hygiene rules plus green molecule cycle per the role's AGENTS.md).
- Verify the archived result.
