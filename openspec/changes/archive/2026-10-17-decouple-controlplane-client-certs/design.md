# Design: Decouple controller-manager and scheduler client-cert re-issues

## Context

`tasks/ipa-controlplane-clients.yml` re-issues the controller-manager and scheduler client
certificates from the `kubeclusteradm` CA (CA #2). Both flows share a single gate: a
read-only extraction of the controller-manager conf's embedded client-certificate issuer
(`cm_swap_needed`), which gates all eight tasks of both components. The file header documents
the intent ("swapped together"), but the components share no state: separate key/CSR/cert
files, separate conf files, separate static pods, separate cert profiles. Profile creation
(`ipa-kubernetes-ca.yml`), CA #2 ACL links (`ipa-kubeclusteradm-ca.yml`), unattended renewal
(`kube-cert-renew.sh.j2`), and the `ipa-pki-swap` verification gates are already
per-component independent.

## Problem

1. **Gratuitous coupling**: no dependency exists between the two flows; sharing a file and a
   gate gives one component's state authority over the other's tasks.
2. **Recovery gap**: the gate is derived from the controller-manager conf only. If the
   controller-manager swap completes and the scheduler swap fails (or the run is interrupted
   between the two), a re-converge sees the controller-manager conf CA #2-signed →
   `cm_swap_needed=false` → the scheduler block is skipped. The scheduler conf keeps the CA #0
   (kubeadm) client cert, which the two-CA client CA bundle does not trust, so the scheduler
   cannot authenticate; the `ipa-pki-swap` "wait for scheduler Ready" gate then fails the run
   with no task left that can repair the scheduler. Manual intervention is required.
3. **Unnecessary churn**: the mirror image (scheduler done, controller-manager failed) makes
   a re-converge regenerate the scheduler key/CSR/cert and restart the scheduler pod even
   though its conf is already CA #2-signed.

## Decision

Split into two self-contained task files, each gated on its own conf:

- `tasks/ipa-controller-manager-client.yml` — gate: extract the embedded client-certificate
  issuer from `/etc/kubernetes/controller-manager.conf` → `cm_swap_needed`; then key, CSR,
  `ipacert` request, re-embed into `controller-manager.conf`, KCM static-pod restart; every
  task `when: cm_swap_needed`. Task names prefixed `Ipa-controller-manager-client`.
- `tasks/ipa-scheduler-client.yml` — gate: same extraction from
  `/etc/kubernetes/scheduler.conf` → `scheduler_swap_needed`; then key, CSR, `ipacert`
  request, re-embed into `scheduler.conf`, scheduler static-pod restart; every task
  `when: scheduler_swap_needed`. Task names prefixed `Ipa-scheduler-client`.

`tasks/ipa-certs.yml` includes the two files sequentially (controller-manager first, then
scheduler) in place of the single include.

### Scheduler gate extraction

kubeadm embeds both the client certificate and the CA in `scheduler.conf` (its static pod
mounts only the conf, not the pki directory), so the controller-manager gate's pattern
applies unchanged:

```yaml
- name: Ipa-scheduler-client | extract scheduler client cert issuer from scheduler.conf
  ansible.builtin.shell: |
    set -o pipefail
    b64=$(grep 'client-certificate-data' /etc/kubernetes/scheduler.conf | awk '{print $2}')
    echo "$b64" | base64 -d > /tmp/scheduler-current.crt
    if openssl x509 -in /tmp/scheduler-current.crt -noout -issuer | grep -q "{{ ipa_kubeclusteradm_ca_name }}"; then
      echo "CA2-SIGNED"
    else
      echo "NOT-CA2"
    fi
  become: true
  changed_when: false
  register: scheduler_cert_issuer
```

Read-only shell (exception rule: no native module extracts an embedded client certificate
from a kubeconfig and reports its issuer); distinct temp file from the controller-manager
gate so the two gates cannot talk over each other.

### Behavior matrix

| Conf state (CM, scheduler) | Before | After |
|---|---|---|
| CA #0, CA #0 (fresh cluster) | both run | both run |
| CA #2, CA #2 (re-converge) | both skip | both skip |
| CA #2, CA #0 (scheduler swap failed) | **scheduler skipped — unrepairable by re-converge** | CM skipped, scheduler re-issued |
| CA #0, CA #2 (CM swap failed) | both re-run (scheduler churns) | CM re-issued, scheduler skipped |

Happy-path behavior is identical; only the partial-failure rows change, and both change in
the recovery direction.

### Ordering and downstream gates

No ordering dependency between the two files; they run sequentially in `ipa-certs.yml`
preserving the current relative order. Downstream verification is unchanged: `ipa-pki-swap`
already gates independently on the KCM lease freshness and the scheduler pod Ready.

## Alternatives Considered

- **Keep one file, add a second gate inside it**: does not address the concern (shared file)
  and still couples the components in one artifact.
- **Shared gate file** (e.g. `ipa-controlplane-clients-gate.yml` computing both flags, then
  two task files): keeps coupling via a shared artifact; the gates are ~12 independent lines
  each, so the duplication cost is trivial compared to the coupling.
- **One `ipacert` call for both**: the module takes one CSR per call; no benefit.

## Risks and Verification

- **Gate equivalence on a fresh cluster**: both confs carry embedded CA #0 client certs, so
  both gates evaluate `NOT-CA2` — exercised by the full-cycle converge.
- **Idempotence**: each file self-gates on a read-only check (`changed_when: false`); the
  `changed_when: true` tasks (re-embed, static-pod restart) remain gated on the swap flag,
  matching the repo's idempotence practice (no blanket suppression on non-read-only
  commands).
- **Lint**: `tox -e lint` (yamllint + flake8 + ansible-lint).
- **Full cycle**: destroy → converge-monorepo → verify-monorepo (parallels scenario).
- **Docs**: role `AGENTS.md` L3 graph update; `update-platform-docs` skill for
  auto-generated blocks.
