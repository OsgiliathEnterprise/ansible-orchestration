# Tasks

## 1. Groundwork: cache convention and variables

- [x] 1.1 Add role defaults for the new credential locations (`kube_scratch_cache_dir: /run/krb5cc`, `kube_unit_state_dir: /var/lib/kube-cert-renew`, idm-side keytab path `{{ kube_unit_state_dir }}/kubeclusteradm.keytab`) and verify with `molecule syntax` (via `uv tool run --python 3.13 --with tox tox -e converge-monorepo -- --scenario-name=<host-os>` syntax phase or `ansible-playbook --syntax-check` equivalent) that the role still parses.
- [x] 1.2 In `tasks/requirements.yml`, create `{{ kube_scratch_cache_dir }}` as a root-owned `0700` directory (`file: state: directory`) and update the ticketing comment to state that ticket acquisition runs through native modules into `/run/krb5cc/<principal>.<purpose>.ccache`; verify by converging `requirements.yml` on any host and checking `stat -c %a /run/krb5cc` is `700`.
- [x] 1.3 Rename/move every existing `krb_ticket` scratch cache under `tasks/` from `/tmp/.*.ccache` dotfiles to `{{ kube_scratch_cache_dir }}/<principal>.<purpose>.ccache` (keeping pre-clear + `changed_when: false`), and verify `grep -rn "ccache" tasks/ | grep /tmp` returns no matches.

## 2. Ordering fix: CA-ACL host grants before node join

- [x] 2.1 Create `tasks/ipa-ca-acl-prejoin.yml`: delegated to idm, admin scratch ticket per the D1 convention, looping the existing check-then-add `tasks/ipa-ca-acl-host.yml` to grant every kube host to `kubernetes-ca-acl` and `kubeclusteradm-acl`; verify with `reconverge` on an already-converged cluster that every grant task reports `ok` (no change).
- [x] 2.2 Wire `ipa-ca-acl-prejoin.yml` into the CA provisioning chain in `tasks/ipa-certs.yml` (after both CAs and their profiles exist, before the node-join include in `tasks/main.yml`), keeping the `ipa-cert-renewal.yml` grant loop as the steady-state re-assert; verify from a fresh `destroy → converge` that no self-enrollment task takes an admin-identity fallback (task names/`when` evaluations in the converge log).

## 3. Node self-enrollment (kube-node-cert)

- [x] 3.1 D2 spike: on a live molecule worker, run `community.crypto.privatekey` + `community.crypto.x509_certificate` (CSR, `O=system:nodes`, CN=hostname) and `freeipa.ansible_freeipa.ipacert` (`ca=kubeclusteradm`, `profile=kubernetesNodes`, `principal=host/<node>`) locally with `env: KRB5CCNAME` from a node-minted keytab ticket, and record whether the module works node-side or the documented shell `ipa cert-request` exception is needed; verify the issued PEM chains to CA #2 on the node.
- [x] 3.2 Rewrite `tasks/kube-node-cert.yml` to the spike outcome: key + CSR + ticket + enrollment all execute on the node; delete the master-side key/CSR generation, idm staging, slurp/copy shuttling, and their cleanup tasks; verify `grep -n "node-.*\\.key\|node-.*\\.csr" tasks/` shows no master-side paths and a fresh converge yields each node's cert at its kubelet client-cert path with the node `Ready`.
- [x] 3.3 Update `molecule/default/tests/test_node.py` (and confirm the `kvm/tests` symlink set still mirrors it) to assert the node client cert/key exist under `/etc/kubernetes/pki/`, the key is `0600` root-owned, and the cert subject carries `O=system:nodes`; verify with `tox -e verify-monorepo -- --scenario-name=<host-os>` green.

## 4. Master self-enrollment and realm-password confinement

- [x] 4.1 In `tasks/ipa-front-proxy.yml`, `ipa-controller-manager-client.yml`, `ipa-scheduler-client.yml`, `kube-apiserver-kubelet-client.yml`, `ipa-api-server.yml`: replace un-delegated `ipacert` calls using `ipaadmin_password` with a master host-keytab `krb_ticket` (`host/<master>`) + ticket-authenticated `ipacert`, mirroring `templates/kube-cert-renew.sh.j2` per cert; verify those files contain no `ipaadmin_password` and a fresh converge issues every cert with the expected principal/CA.
- [x] 4.2 In `tasks/ipa-kube-admin-credential.yml` (and any remaining offenders found by `grep -rn ipaadmin_password tasks/`): delegate admin-identity FreeIPA API module calls to idm with an admin scratch ticket, keeping the managed password only where the spec requires a fallback branch (key-setting flow, `kubeclusteradm` enrollment); verify no task targeting a kube host (not delegated to idm) references `ipaadmin_password`.

## 5. Runtime hygiene: timer cache, keytab off /tmp

- [x] 5.1 Add `StateDirectory=kube-cert-renew` and `Environment=KRB5CCNAME=FILE:/var/lib/kube-cert-renew/ccache` to `templates/kube-cert-renew.service.j2`, and pre-clear that cache at the top of `templates/kube-cert-renew.sh.j2`; verify on a converged host that a manual `systemctl start kube-cert-renew` writes its ticket only under `/var/lib/kube-cert-renew/` (check `find /tmp -name 'krb5cc*' -newer …` stays empty during the run) and the service exits 0.
- [x] 5.2 In `tasks/ipa-cert-renewal.yml`: export the keytab directly to `/var/lib/kube-cert-renew/kubeclusteradm.keytab` on idm (dir `0700`, file `0600` via `umask`/`file` after `kadmin.local ktadd -norandkey`), replace the `base64 -w0` shuttle with `slurp` + `copy: content:` to the master's credential folder (mode `0600`), and add a cleanup `file: state: absent` for the legacy `/tmp/kubeclusteradm.keytab`; verify `ls -l` on idm shows `0600 root` at the new path, no keytab under `/tmp`, and the point-in-time probes in `ipa-kube-admin-credential.yml` still pass.
- [x] 5.3 Delete the sacrificial host-keytab probe (and its unregistered-consumer variable) in `tasks/ipa-certs.yml`; verify `grep -n "kca_keytab_usable" tasks/ipa-certs.yml` is empty and converge stays green.

## 6. Documentation

- [x] 6.1 Update this role's `AGENTS.md` — Kerberos Ticketing section (new `/run/krb5cc/<principal>.<purpose>.ccache` convention, unit-scoped runtime cache, keytab at `/var/lib/kube-cert-renew`) and the L3 task-flow graph (add `ipa-ca-acl-prejoin.yml`; reflect rewritten `kube-node-cert.yml` as node-local); verify every path in the graph resolves to an existing file and each changed claim is checkable in the code.

## 7. Integration verification

- [x] 7.1 Full cycle on the host-OS scenario: `destroy → converge-monorepo → verify-monorepo` green from scratch, then re-converge and re-verify for idempotence (no drift, no changed tasks on steady state); per monorepo rules, do not treat converge exit 0 alone as success — the verify suite is the gate.
- [x] 7.2 Invariant greps as a final guard: `grep -rn "kinit\|klist\|kdestroy" tasks/` empty; no `.ccache` under `/tmp` in `tasks/`; no `ipaadmin_password` on non-idm-delegated kube-host tasks; `openspec validate principals-in-place --strict` clean.

## Workflow follow-up

- Archive the change (`/opsx-archive`) after review requirements are satisfied, then re-run `openspec list --specs` to confirm the five main specs absorbed the deltas.
- Run `/update-platform-docs` if the platform docs surface any of the touched variables/paths.
