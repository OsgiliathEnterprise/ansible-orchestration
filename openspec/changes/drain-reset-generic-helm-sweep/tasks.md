# Tasks: Drain-Reset Generic Helm Sweep

## 1. Variables

- [ ] 1.1 Add `helm_version` (pinned to a current stable v3) to `defaults/main.yml`. Verify: `grep helm_version defaults/main.yml` shows the pinned value.

## 2. Helm CLI installation (`tasks/drain-and-reset.yml`)

- [ ] 2.1 Add a `stat` task checking `/usr/local/bin/helm` and a `get_url` + `unarchive` task pair (task-local `helm_arch` var mapped from `ansible_arch`: `x86_64`/`amd64`→`amd64`, `aarch64`/`arm64`→`arm64`) that installs the binary to `/usr/local/bin/helm`, `become: true`, `when:` the stat is negative, **without** `failed_when: false`. Verify: on a fresh master the tasks install and `helm --version` succeeds on the master; on a second run the install tasks are skipped (skipped stats, not changed) and the binary is untouched.

## 3. Discovery and uninstall

- [ ] 3.1 Add the discovery task `ansible.builtin.command: helm list -A --all -o json --kubeconfig {{ kube_config_path }}` with `become: true`, `changed_when: false`, `failed_when: false`, registered as `_helm_releases`. Verify: on a release-free cluster the task is ok and `stdout` parses to `[]`; after `helm install`ing a test chart on the master, `stdout` contains that release's `name` and `namespace`.
- [ ] 3.2 Add the uninstall task `kubernetes.core.helm` with `name: "{{ item.name }}"`, `namespace: "{{ item.namespace }}"`, `release_state: absent`, `wait: false`, `kubeconfig: "{{ kube_config_path }}"`, `become: true`, `failed_when: false`, looping over `(_helm_releases.stdout | default('[]') | from_json) | selectattr('status', 'in', ['deployed', 'failed']) | list`. Verify: with a test release present, the loop runs once per release and `helm list -A --all` shows it as `uninstalled` afterwards; on a release-free cluster the loop is a no-op (skipped).

## 4. Removal of hard-coded istio tasks

- [ ] 4.1 Delete the four `Drain-and-reset | remove charts with disruption budget (istio-*)` tasks from `tasks/drain-and-reset.yml`. Verify: `grep -ci istio tasks/drain-and-reset.yml` returns 0 and the file still contains the drain, node-deletion, and `kubeadm reset` tasks in order.

## 5. Lint and end-to-end verification

- [ ] 5.1 Run `ansible-lint` on the role. Verify: no new findings in `tasks/drain-and-reset.yml` or `defaults/main.yml`.
- [ ] 5.2 Run the full destroy + converge + verify cycle (`tox -e destroy` then `tox -e converge-monorepo` then `tox -e verify-monorepo`, `--scenario-name=parallels`). Verify: the destroy path logs show the install (skipped if pre-seeded), the list task registering `[]`, the uninstall loop as a no-op, and no istio task; converge and verify pass at the baseline (32/32).
- [ ] 5.3 Exercise the sweep against a real release: `helm install` a small test chart on the master, then re-run the destroy path. Verify: the uninstall loop iterates for the test chart before the drain task and `helm list -A --all` no longer lists it as `deployed`/`failed` afterwards.
