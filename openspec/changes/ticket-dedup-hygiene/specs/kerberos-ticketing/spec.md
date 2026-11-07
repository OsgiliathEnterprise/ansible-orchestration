# Spec Delta: kerberos-ticketing

## MODIFIED Requirements

### Requirement: Realm admin password is confined to the control node and the IPA server
Tasks that authenticate to the FreeIPA API with realm-admin rights SHALL run delegated to the IPA server and authenticate with an `admin` scratch ticket (module-acquired, `env: KRB5CCNAME`), following the existing scratch-cache convention. No task targeting a Kubernetes master or worker host SHALL pass `ipaadmin_password` (or otherwise deliver the realm admin password to that host). This confinement covers ticket acquisition itself: no `community.general.krb_ticket` task minting an `admin` (or other privileged) ticket with a `password:` argument SHALL run targeted at a kube host — such acquisitions SHALL be delegated to the IPA server, so the realm admin password is never presented to the KDC from a Kubernetes host by any module or shell path.

#### Scenario: No admin password on kube hosts
- **WHEN** the task files under `tasks/` are reviewed after the change
- **THEN** no task with a kube host as target (not delegated to the IPA server) references `ipaadmin_password`

#### Scenario: No privileged password ticket on kube hosts
- **WHEN** the task files under `tasks/` are audited for `community.general.krb_ticket` tasks that carry a `password:` argument
- **THEN** every such task minting a privileged (admin-equivalent) ticket is delegated to the IPA server, and no CA-download or other admin-identity consumer authenticates with a kube-host-local ticket cache

#### Scenario: Admin API operation runs on idm with a scratch ticket
- **WHEN** a converge-time flow needs realm-admin rights against the FreeIPA API
- **THEN** the task is delegated to the IPA server, a pre-cleared `admin` scratch ticket under `/run/krb5cc` is acquired there, and the task inherits it via `env: KRB5CCNAME`

## ADDED Requirements

### Requirement: One scratch ticket per principal, host and purpose phase
Within a single purpose phase of a converge, the role SHALL mint one scratch ticket per (principal, host, credential source) at the head of the phase and share it across that phase's tasks via `env: KRB5CCNAME`, instead of re-minting an identical ticket per task file. Each shared cache SHALL be pre-cleared before its single acquisition. Re-acquisition per file is reserved for phases where the credential state can legitimately change between uses.

#### Scenario: Control-plane cert enrollments share one host ticket
- **WHEN** the master enrolls the apiserver, front-proxy, controller-manager, scheduler, and kubelet-client certificates during one converge
- **THEN** exactly one `host/<master>` scratch ticket is minted from the master's keytab for the enrollment phase, all five enrollments authenticate with it via `env: KRB5CCNAME`, and no per-file pre-clear+acquire pair remains in those five task files

#### Scenario: Shared ticket is still fresh
- **WHEN** a converge re-runs while the phase's shared scratch cache still exists on disk
- **THEN** the pre-clear before the phase's single acquisition removes the stale cache and a fresh ticket is minted

#### Scenario: Keytab re-export phase re-probes rather than shares
- **WHEN** a phase gates an action on the current usability of a keytab (for example, deciding whether to re-export the `kubeclusteradm` keytab)
- **THEN** that phase runs its own keytab-usability probe instead of reusing a fact captured by an earlier phase, since the keytab state can change between phases

#### Scenario: Runtime renewal matches the converge-time shape
- **WHEN** the certificate-renewal script renews the master's control-plane certificates
- **THEN** it authenticates all host-principal renewals of the tick with a single host-principal ticket, mirroring the converge-time shared-ticket convention
