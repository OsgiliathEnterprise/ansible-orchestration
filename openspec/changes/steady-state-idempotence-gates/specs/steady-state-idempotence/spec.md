# Steady State Idempotence

## ADDED Requirements

### Requirement: Steady-state converge reports no change on unchanged infrastructure
A converge of the role onto a healthy, up-to-date cluster — all cluster certificates valid beyond the renewal threshold and already issued by the expected IPA CAs, `admin.conf` embedding the current client certificate, the cluster CA bundle already holding the IPA-issued CA, and the NFS PersistentVolume already matching its rendered spec — SHALL report zero changed tasks (the only permitted changed task being the read-only `kubectl get nodes` verification command, which truthfully reports `changed`). Tasks in such a converge MUST NOT be suppressed with blanket `changed_when` overrides.

#### Scenario: Clean reconverge on a healthy cluster
- **WHEN** the role converges successfully and a second converge is executed with no infrastructure change
- **THEN** the second converge's changed-task list is empty apart from the `kubectl get nodes` verification command
- **AND** every molecule verify gate still passes (all nodes Ready, per-pod evidence, PV mount)

#### Scenario: No blanket change masking
- **WHEN** a task in the converged task file set would unconditionally mutate state
- **THEN** that task is either idempotent by construction or gated on a read-only check
- **AND** no task uses `changed_when: false` or `changed_when: true` purely to hide its change status (blanket suppression is permitted only on strictly read-only commands)

### Requirement: Certificate gates replay on expiry or CA re-issuance
Every issuance gate and every manifest-move gate that decides whether an IPA-issued certificate task or a kubeconfig/manifest redeploy runs SHALL evaluate, from on-disk state, all of: the current certificate's issuer matches the expected IPA CA for that principal (CA #1 `kubernetes-ca` for serving certificates, CA #2 `kube-clusteradm-ca` for client certificates); the current certificate's `not_after` exceeds the configured renewal threshold; and the issuing CA's `not_after` exceeds the same threshold. A gate MUST NOT skip issuance or redeploy while any of these conditions fails, and MUST NOT depend on any marker written by a previous converge run.

#### Scenario: Near-expiry certificate re-issues
- **WHEN** a converged host holds an IPA-issued cluster certificate whose `not_after` is within the renewal threshold
- **THEN** the converge re-issues that certificate (the gate replays, it does not skip)

#### Scenario: Foreign-issuer certificate is replaced
- **WHEN** an on-disk cluster certificate was issued by a CA other than the expected IPA CA for that principal (for example a surviving kubeadm self-signed certificate)
- **THEN** the converge re-issues it from the expected IPA CA and redeploys every dependent kubeconfig or manifest

#### Scenario: CA approaching expiry replays the swap
- **WHEN** an IPA issuing CA's `not_after` is within the renewal threshold
- **THEN** the dependent issuance and swap tasks replay instead of being skipped, so the converge remains a repair path when the out-of-band renewal timer has failed

### Requirement: Renewal threshold has a single source of truth
The certificate renewal threshold SHALL be defined once as a role default (in days) and every component that compares certificate validity against it — the converge-time gates and the per-host renewal timer script — SHALL render their threshold from that single default. A change to the default SHALL NOT require editing any task file or template body.

#### Scenario: Threshold default drives converge and timer
- **WHEN** an operator overrides the threshold default
- **THEN** the converge-time gates and the renewal timer script both evaluate expiry against the overridden value

### Requirement: Read-only status output markers drive truthful change reporting
Tasks that conditionally mutate state via an imperative helper script SHALL report change truthfully by having the helper emit a deterministic marker token on stdout when and only when it performed a mutation, and the task registering stdout and deriving `changed_when` from the marker's presence. Check-then-add idempotent operations (CA ACL host grants, service-category sets) SHALL follow the existing marker convention (`CA-ACL-ADDED`, `SERVICECAT-SET`). Read-only status inspection may use `changed_when: false`.

#### Scenario: No-op add reports ok
- **WHEN** an add-type task runs and the desired entry is already present
- **THEN** the helper emits no marker token and the task reports `ok`

#### Scenario: Real add reports changed
- **WHEN** an add-type task runs and the helper performs a mutation
- **THEN** the helper emits its marker token and the task reports `changed`

### Requirement: Repair paths bypass gates
Gates SHALL evaluate current on-disk/cluster state as their sole input, so that any manual change to that state is detected and repaired by the next converge. Reset/delete flows (under `reset: true`) are non-idempotent by design and are exempt from this capability's requirements.

#### Scenario: Externally deleted manifest is restored
- **WHEN** an operator deletes the controller-manager or scheduler kubelet manifest from a converged master
- **THEN** the next converge's manifest-move gate observes the missing file and redeploys it
