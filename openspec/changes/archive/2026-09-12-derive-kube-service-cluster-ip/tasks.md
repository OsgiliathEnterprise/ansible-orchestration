# Tasks: Derive Kube Service Cluster IP

## 1. Implementation

- [x] 1.1 In `tasks/ipa-kubernetes-ca.yml`, change the `line:` value of the `Ipa-kubernetes-ca | add kube service cluster IP to IPA server hosts for Dogtag reachability check` task from `"10.96.0.1 {{ orchestration_host_hostname }}"` to `"{{ ((kube_service_cidr | default('10.96.0.0/12')) | ansible.utils.next_nth_usable(1)) }} {{ orchestration_host_hostname }}"` (the idiom used by the six other consumers). Verify: `grep -c '10\.96\.0\.1' tasks/ipa-kubernetes-ca.yml` returns 0 (no hard-coded IP left in the file) and the task's `line:` contains `next_nth_usable(1)`.

## 2. Verification

- [x] 2.1 Run `ansible-lint` on the role and `ansible-playbook --syntax-check` on `molecule/parallels/converge.yml`. Verify: no new lint findings and the syntax check passes (the template expression is valid).
- [ ] 2.2 Confirm default-CIDR behavior is unchanged: after a converge, the first IPA server's `/etc/hosts` contains the line `10.96.0.1 <orchestration_host_hostname>`. Verify: `grep '10.96.0.1' /etc/hosts` on the IPA server (delegated, become) shows the entry, identical to pre-change output.
