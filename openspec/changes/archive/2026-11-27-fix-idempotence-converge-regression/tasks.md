# Tasks

## 1. Restore the restart guarantee

- [x] 1.1 Add `- name: Fix Requirements | flush containerd handlers` (`ansible.builtin.meta: flush_handlers`) at the end of `tasks/fix-requirements.yml`, after `Fix Requirements | Deploy containerd configuration`
- [x] 1.2 Extend the `tasks/fix-requirements.yml` header comment to document the flush as load-bearing (the invariant that regressed)

## 2. Verify on the host-OS-matched scenario (parallels)

- [x] 2.1 `tox -e destroy -- --scenario-name=parallels`
- [x] 2.2 `tox -e converge-monorepo -- --scenario-name=parallels` — master `kubeadm init` succeeds first attempt, `kubernetesNodes` profile created, both workers pass the profile gate and join
- [x] 2.3 `tox -e verify-monorepo -- --scenario-name=parallels` — all nodes Ready, per-pod evidence, PV mounts green
- [x] 2.4 Reset-path reconverge (`converge-monorepo`, `reset_kube: True` per converge.yml) green (`failed=0`); no-reset steady-state reconverge (`-e reset_kube=false`) reports **all-changed=0** on master/node1/node2; `verify-monorepo` green again (76/76)
