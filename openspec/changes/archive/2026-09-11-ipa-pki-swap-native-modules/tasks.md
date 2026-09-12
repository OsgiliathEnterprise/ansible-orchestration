## 1. Nativization of ipa-pki-swap.yml (requires change `ipa-certs-native-modules` for the readiness variables)

- [x] 1.1 Replace the sed-loop task (L3-12) with a single `ansible.builtin.replace` task looping over the four kubeconfig files (`controller-manager.conf`, `scheduler.conf`, `kubelet.conf`, `admin.conf`) using an indentation-preserving backreference; verify after converge that patched lines keep their original indentation and a re-run reports ok (not changed)
- [x] 1.2 Delete the dead user-kubeconfig patch task (L24-33); verify no references remain and the `/root/.kube/config` symlink task (L35-41) stays intact
- [x] 1.3 Remove `changed_when: true` from the two server-URL `replace` tasks (L43-57) so re-runs report ok
- [x] 1.4 Replace the three `touch` shell tasks (L59-63, L73-83) with `ansible.builtin.file state=touch`; verify the static pods restart and become healthy after converge

## 2. Readiness waits

- [x] 2.1 Replace both port-based `wait_for` tasks (L65-71, L85-91) with `/healthz` `uri` polls using the `kubernetes_api_*` variables from change `ipa-certs-native-modules`; verify both pass during converge

## 3. Controller-manager readiness

- [x] 3.1 Replace the `seq`/`sleep` shell loop (L93-105) with a single registered kubectl command plus native `retries: 12`, `delay: 10`, `until: "'True' in <reg>.stdout"`; verify it passes during converge and that the task fails (not hangs) if the controller-manager never becomes Ready

## 4. Idempotent kubelet patch

- [x] 4.1 Update the copied Python script to compare desired vs current `apiServerOverride` values, print `CHANGED`/`UNCHANGED`, and write only on difference (drop the unused `import os`); verify first converge prints CHANGED and `/var/lib/kubelet/config.yaml` carries the expected override
  - **Adapted**: implemented as a single `ansible.builtin.blockinfile` (marker `# {mark} API server override (ipa-pki-swap)`, `insertafter: EOF`) instead of a Python script. Rationale: the kubeadm-generated config has no `apiServerOverride:` anchor, so line-in-file patching appends at EOF and produces invalid YAML (discovered during 5.1 verification — the kubelet crash-looped on the malformed block). The block is a valid top-level `KubeletConfiguration` field and blockinfile is marker-idempotent by construction.
- [x] 4.2 Set `changed_when: "'CHANGED' in <reg>.stdout"` on the patch task; make the kubelet restart conditional (`when: <patch> is changed`) and remove its `changed_when: true`; verify a second converge reports the patch ok and does not restart kubelet
  - **Adapted**: the blockinfile task is idempotent by construction (no `changed_when` needed); the kubelet restart is conditional via `notify: ansible-orchestration | refresh kube` on the block task — the handler fires only when the block is changed (notify semantics = "restart iff changed"), matching the role's existing handler idiom and the `no-handler` lint rule. Idempotence re-run: block task `ok`, handler not notified, no kubelet restart.

## 5. Verification

- [x] 5.1 Run full converge (`tox -e converge-monorepo --scenario-name=parallels`) and confirm success with all rewritten tasks reporting as expected
- [x] 5.2 Run the idempotence check (second converge) and confirm every task rewritten in this change reports ok/no-change, including no kubelet restart
  - **Adapted**: a literal second full converge cannot be no-change because `converge.yml` hardcodes `reset_kube: True` (full teardown + rebuild; the role's documented cycle is destroy → converge → verify, no idempotence step). Instead, re-ran `tasks/ipa-pki-swap.yml` standalone against the converged cluster with the role defaults/vars/facts passed explicitly: `ok=14 changed=3 failed=0 skipped=0` — the only `changed` tasks are the three documented `file state=touch` tasks.
  - **Handler semantics verified (final design)**: full converge log shows `Block inserted` (changed) → verify `ok` → `RUNNING HANDLER [tcharl.ansible_orchestration : Handler | refresh kube]` at play end (kubelet restarted, new MainPID, `ActiveState: active`). Idempotence re-run: block task `ok` (no re-patch), **no handler notified** (no `RUNNING HANDLER` line), kubelet MainPID/ActiveEnterTimestamp unchanged.
  - **Environment notes**: during the handler-version converge, an unrelated Calico `install-cni` init-container race (CrashLoopBackOff until `10-calico.conflist` was stably written) left both nodes `NotReady` for ~13 min; self-healed — both nodes `Ready`, all `calico-system` pods `Running` afterwards. `tox -e lint` fails on a pre-existing `risky-file-permissions` violation in `tasks/ipa-certs.yml:157` (file unmodified by this change; gate was already red at HEAD). This change's file passes ansible-lint at the `production` profile with 0 failures.
