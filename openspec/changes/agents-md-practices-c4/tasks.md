## 1. Master AGENTS.md — Practices section

- [ ] 1.1 Add a `## Practices` section to `ansible/roles/AGENTS.md` with the native-module preference table (pattern → module mapping per design D2: touch/sed/cat/polling/cert-inspection/kubectl) and the shell-exception rule (comment required when no native equivalent exists); verify each table row maps a pattern actually observed in this repo's task files
- [ ] 1.2 Add the idempotency convention (no `changed_when` masking of non-idempotent shell; read-only commands may use `changed_when: false`) and the no-dead-code rule (every included task file referenced, every registered variable consumed) to the same section; verify both rules are stated with a concrete example each

## 2. Master AGENTS.md — C4 architecture

- [ ] 2.1 Add an `## Platform Architecture (C4)` section to `ansible/roles/AGENTS.md` with the L1 context diagram (Ansible control node → idm / master / node1 VMs); verify hostnames match `molecule/parallels/converge.yml` and the role AGENTS.md topology table
- [ ] 2.2 Add the L2 container diagram (per-host services and ports: FreeIPA HTTP/LDAP/KDC on idm, K8s static pods + kubelet + containerd on master :6443, NFS server export `/var/nfs/volume` on idm mounted at `/net` on master); verify every port/path against the task files before including it
- [ ] 2.3 Add the dual-CA PKI trust diagram (IPA `kubernetes-ca` signs component certs; kubeadm self-signed CA kept as `ca.crt.kubeadm`, controller-manager keeps signing cluster certs with it; API server trusts both via `--client-ca-file=ca-bundle.crt`) to the same section; verify against `tasks/ipa-certs.yml`

## 3. Role AGENTS.md — L3 task flow

- [ ] 3.1 Add an L3 task-flow graph (`main.yml` → include files, master-only vs node-only branches) to `tcharl.ansible_orchestration/AGENTS.md`, and a one-line pointer from the master C4 section; verify every file listed in the graph exists under `tasks/`

## 4. Verification

- [ ] 4.1 Render-check both edited AGENTS.md files (valid markdown, no broken relative links) and confirm each diagram fact is traceable to code; deliverable = the two updated files with all sections present
