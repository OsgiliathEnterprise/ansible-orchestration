## 1. Variables

- [ ] 1.1 Add `kubernetes_api_host` (`"127.0.0.1"`), `kubernetes_api_port` (`6443`), `kubernetes_api_ready_retries` (`12`), `kubernetes_api_ready_delay` (`10`) to `defaults/main.yml`; verify they resolve in a playbook run (debug task or syntax check)

## 2. Nativization of ipa-certs.yml

- [ ] 2.1 Replace the CA-bundle `cat` shell task (L44-49) with two `slurp` tasks + one `copy content=` (`owner: root`, `mode: '0644'`); verify after converge that `ca-bundle.crt` contains exactly 2 certificates (`openssl crl2pkcs7 -nocrl -certfile ca-bundle.crt | openssl pkcs7 -print_certs`)
- [ ] 2.2 Replace the controller-manager `sed` shell task (L66-74) with three `ansible.builtin.replace` tasks (client-ca-file, cluster-signing-cert-file, root-ca-file); verify after converge that the manifest carries the expected flags and a second run reports ok (not changed) for these tasks
- [ ] 2.3 Replace the scheduler grep-guarded `sed` task (L76-84) with a single unguarded `replace` task; verify same behavior on both fresh and re-run converge
- [ ] 2.4 Replace the port-based `wait_for` (L86-92) with a `/healthz` `uri` poll using the new variables (`validate_certs: no`, retries/delay from defaults), and variabilize the existing healthz wait (L139-148); verify both waits pass during converge
- [ ] 2.5 Replace the `touch` shell task (L133-137) with `ansible.builtin.file state=touch`; verify the API server static pod restarts and becomes healthy after the swap
- [ ] 2.6 Add an exception comment to the `openssl verify` task (L150-158) stating no native chain-validation module exists in community.crypto 3.3.0; verify the comment is present and the task code is otherwise unchanged

## 3. kubectl consolidation

- [ ] 3.1 Consolidate the duplicate best-effort `kubectl cluster-info` tasks (L160-180) into one retried task (`retries: 3`, `delay: 10`, `failed_when: false`, registered) plus a single debug print of its output; verify converge output shows exactly one `cluster-info` invocation

## 4. Spec delta

- [ ] 4.1 Verify the MODIFIED requirement in `specs/ipa-pki-bootstrap/spec.md` passes `openspec validate ipa-certs-native-modules`

## 5. Verification

- [ ] 5.1 Run full converge (`tox -e converge-monorepo --scenario-name=parallels`) and confirm success with all rewritten tasks reporting as expected
- [ ] 5.2 Run the idempotence check (second converge) and confirm every task rewritten in this change reports ok/no-change
