## 1. Nativization of ipa-pki-swap.yml (requires change `ipa-certs-native-modules` for the readiness variables)

- [ ] 1.1 Replace the sed-loop task (L3-12) with a single `ansible.builtin.replace` task looping over the four kubeconfig files (`controller-manager.conf`, `scheduler.conf`, `kubelet.conf`, `admin.conf`) using an indentation-preserving backreference; verify after converge that patched lines keep their original indentation and a re-run reports ok (not changed)
- [ ] 1.2 Delete the dead user-kubeconfig patch task (L24-33); verify no references remain and the `/root/.kube/config` symlink task (L35-41) stays intact
- [ ] 1.3 Remove `changed_when: true` from the two server-URL `replace` tasks (L43-57) so re-runs report ok
- [ ] 1.4 Replace the three `touch` shell tasks (L59-63, L73-83) with `ansible.builtin.file state=touch`; verify the static pods restart and become healthy after converge

## 2. Readiness waits

- [ ] 2.1 Replace both port-based `wait_for` tasks (L65-71, L85-91) with `/healthz` `uri` polls using the `kubernetes_api_*` variables from change `ipa-certs-native-modules`; verify both pass during converge

## 3. Controller-manager readiness

- [ ] 3.1 Replace the `seq`/`sleep` shell loop (L93-105) with a single registered kubectl command plus native `retries: 12`, `delay: 10`, `until: "'True' in <reg>.stdout"`; verify it passes during converge and that the task fails (not hangs) if the controller-manager never becomes Ready

## 4. Idempotent kubelet patch

- [ ] 4.1 Update the copied Python script to compare desired vs current `apiServerOverride` values, print `CHANGED`/`UNCHANGED`, and write only on difference (drop the unused `import os`); verify first converge prints CHANGED and `/var/lib/kubelet/config.yaml` carries the expected override
- [ ] 4.2 Set `changed_when: "'CHANGED' in <reg>.stdout"` on the patch task; make the kubelet restart conditional (`when: <patch> is changed`) and remove its `changed_when: true`; verify a second converge reports the patch ok and does not restart kubelet

## 5. Verification

- [ ] 5.1 Run full converge (`tox -e converge-monorepo --scenario-name=parallels`) and confirm success with all rewritten tasks reporting as expected
- [ ] 5.2 Run the idempotence check (second converge) and confirm every task rewritten in this change reports ok/no-change, including no kubelet restart
