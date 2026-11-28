# Tasks

## 1. CA-fetch drift gate + idm tempdir shuttle (design D1–D3)

- [x] 1.1 In `tasks/certs/ipa-certs.yml`, add the read-only drift gate before the fetch section: `stat` + `community.crypto.x509_certificate_info` on the installed `ca.crt.new` / `ca.crt.kubeclusteradm`, idm-delegated `ipa ca-show <ca> | openssl x509 -noout -fingerprint -sha256 | tr -d ':' | tr '[:upper:]' '[:lower:]'` probes (`changed_when: false` + read-only comment, probe failure fails the task), and `set_fact kube_ca_fetch_needed`. Verify: `ansible-lint` clean; a converged master's reconverge log shows the probes ok and the fetch block skipped.
- [x] 1.2 Wrap the fetch section (`tempfile` dir 0700 on idm → two `ipa ca-show --certificate-out` shells without `changed_when: false` → slurps → master-side installs → `file: state: absent` on the registered dir) in `when: kube_ca_fetch_needed | bool`; keep `env: KRB5CCNAME` and `set -o pipefail`. Verify: on a fresh converge the block runs and reports changed on the fetches/installs; on a no-op reconverge every block task is skipped.
- [x] 1.3 Add the documented legacy sweep `file: state: absent` for `/run/ipa-ca-fetch` (delegated idm, root) and delete `kube_idm_ca_fetch_dir` + its comment block from `defaults/main.yml`; grep-verify zero remaining references to the variable or path outside the sweep task. Verify: a host left with `/run/ipa-ca-fetch` converges it away (changed once, then ok); `grep -rn 'kube_idm_ca_fetch_dir\|ipa-ca-fetch' tasks/ defaults/ molecule/` shows only the sweep.

## 2. Node-join fetches on shared idm (design D4)

- [x] 2.1 In `tasks/kube-install-join-node.yml`, replace `/tmp/kube-node-ca.crt` / `/tmp/kube-node-ca-clusteradm.crt` with the registered idm tempdir paths (tempfile at the top of the fetch sub-flow, removed after the last slurp); keep the retry loops' `changed_when: false` with their read-only justification comments; update both `CA_FETCH_TIMEOUT` fail messages to name the registered path. Verify: a fresh converge joins with per-run paths (converge log shows the generated dir names, no `/tmp/kube-node-ca*` strings); reconverge skips the whole not-joined block.
- [x] 2.2 Convert the node-local `/tmp/kube-node-ca-expected.crt` compare file to a registered `tempfile` (state: file) consumed by the `diff -q` loop and removed by the cleanup task. Verify: after a join converge, `ls /tmp/kube-node-ca-expected.crt` on the node fails; the remap-race loop still retries against the installed file.

## 3. Admin enrollment staging (design D5)

- [x] 3.1 In `tasks/admin-user.yml`, replace `/tmp/kube-admin-enroll.csr` / `.crt` with a registered idm tempdir (`<tmp>/enroll.csr`, `<tmp>/enroll.crt`); make the "clean up staged temp files" task a `file: state: absent` on the registered dir guarded by the registered fact being defined. Verify: fresh converge enrolls and leaves no `/tmp/kube-admin-enroll.*` on idm; reconverge (cert exists) executes zero tempfile/cleanup tasks.

## 4. Profile import scratch (design D6)

- [x] 4.1 In `tasks/certs/ipa-ca-profile.yml`, mint a registered idm tempfile (`prefix: profile-<id>-`, `suffix: .cfg`) inside the `rc == 2` block, point `certprofile-show --out` / `lineinfile` / `certprofile-import --file` at `.path`, and delete it at the end of the block; remove the `ipa_ca_profile_file` input from the header comment and the four passings in `tasks/certs/ipa-kubernetes-ca.yml`. Verify: `grep -rn 'ipa_ca_profile_file\|_ca_profile.cfg' tasks/` is empty; with a profile deleted (`ipa certprofile-del kubeScheduler` on idm), reconverge recreates it and leaves no `/tmp/profile-*` / `/tmp/ipa_*_ca_profile.cfg` residue.

## 5. Gate anchor as run-scoped tempfile (design D7)

- [x] 5.1 In `tasks/certs/ipa-certs.yml`, mint the anchor as `tempfile` (`prefix: kube-api-gate-anchor-`, `suffix: .crt`) registered `kube_gate_anchor_tmp` before the gated build, write the copy to `.path`, and make the healthz `uri` `ca_path` consume the registered path with the existing bundle fallback (`is not skipped` / `is defined` guards). Verify: a fresh converge passes the healthz gate through the generated path; a steady-state gate pass reads the bundle.
- [x] 5.2 In `tasks/certs/ipa-pki-swap.yml`, drop `/tmp/kube-api-gate-anchor.crt` from the end-of-swap deletion loop and delete the registered anchor path when defined; update `molecule/default/tests/test_master.py` from the fixed-path assert to a `/tmp` prefix no-residue assert on `kube-api-gate-anchor-`. Verify: `pytest` syntax-clean locally; after `verify-monorepo`, the prefix assert passes and no `kube-api-gate-anchor*` exists in `/tmp`.

## 6. Helm shuttle (design D8)

- [x] 6.1 In `tasks/drain-and-reset.yml`, mint a registered tempdir under the same `when: not _helm_bin_stat.stat.exists` gate and point `get_url` dest, `unarchive` dest, and the helm `copy` src at it; remove the registered dir at the end of the gated set (defined-guard). Verify: with `/usr/local/bin/helm` removed on master, converge re-installs it and leaves no `/tmp/helm-*` tarball or `/tmp/linux-*/` dir; normal converge skips every task in the set.

## 7. Integration verification

- [x] 7.1 Run the full molecule cycle on the host-OS-matched scenario (macOS → `parallels`): `destroy → converge-monorepo → verify-monorepo`, then a reconverge (AGENTS.md fallback — molecule `converge.yml` hardcodes `reset_kube: True`, so every molecule converge is a full reset+rebuild and "zero changed" is not achievable there; the reconverge gate is determinism: failed=0, identical recap, verify green). Prove the no-op steady state separately with the same playbook run once with `-e reset_kube=false` (extra-vars override the play var): the CA-fetch block skipped by fingerprint match, all other gated blocks (anchor, node-fetch, admin-enroll, profile `.cfg`, helm) skipped, and zero tempfile tasks executed; idm and the kube hosts hold no shuttle residue (spec scenarios "Successful converge leaves hosts clean" and "No-op reconverge mints no tempfiles").
