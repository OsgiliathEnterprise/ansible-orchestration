# Spec Delta: kerberos-ticketing

## MODIFIED Requirements

### Requirement: Ticket acquisition uses native Ansible negotiation, not shell kinit
The role SHALL acquire every Kerberos ticket with `community.general.krb_ticket` into a dedicated scratch cache under `/run/krb5cc` (a root-only, mode-`0700` directory on tmpfs), named `<principal>.<purpose>.ccache` so the cache identity encodes the Kerberos principal and the purpose it serves — not the calling task file. Every scratch cache SHALL be pre-cleared (`file: state: absent`) before acquisition. No task under `tasks/` SHALL invoke `kinit`, `klist`, or `kdestroy` via `shell`, and no flow SHALL depend on the ambient per-user ticket cache (`~/.k5.<user>`). The role's shell-exception list SHALL NOT contain a ticketing exception; the comment in `tasks/requirements.yml` SHALL state that ticket acquisition runs through native modules.

#### Scenario: Full converge without shell kinit
- **WHEN** the role converges end to end
- **THEN** `grep -rn "kinit\|klist\|kdestroy" tasks/` returns no matches, and every Kerberos-authenticated `ipa`/`ipa_getkeytab`/`ipacert` task ran with a module-acquired scratch cache exported via `env: KRB5CCNAME`

#### Scenario: Stale scratch cache cannot be reused
- **WHEN** a converge is re-run while a scratch cache from a previous run still exists
- **THEN** the pre-clear task removes it before acquisition, the fresh ticket is written to a clean cache, and no task can silently proceed on an expired ticket

#### Scenario: Cache name identifies principal and purpose
- **WHEN** any converge-time scratch ticket is inspected on its host
- **THEN** it lives under `/run/krb5cc/` with a name of the form `<principal>.<purpose>.ccache`, and no provisioning scratch cache is written under `/tmp`

### Requirement: Certificate enrollment uses the native ipa module with a delegated scratch ticket
The role SHALL enroll and issue FreeIPA certificates with the native `freeipa.ansible_freeipa.ipacert` module (GSSAPI negotiation via `KRB5CCNAME`), not shell `ipa` calls and not the nonexistent `community.general.ipa_getcert`. Enrollment of a certificate that a host will use SHALL authenticate as **that host's own principal** — a ticket minted on the owning host from its own `/etc/krb5.keytab` (`krb_ticket` with `keytab: true`) — not as an admin ticket minted elsewhere. Enrollment of the `kubeclusteradm`-principal CSR SHALL authenticate as `kubeclusteradm` (keytab ticket with password fallback). The private key and CSR for a certificate SHALL be generated on the host that will use the certificate, and the private key MUST NEVER leave that host; only the CSR is sent to the CA and only the issued PEM returns.

#### Scenario: Node client cert via keytab
- **WHEN** a worker node needs its client certificate
- **THEN** the ticket authenticating the enrollment is minted on the node itself from the node's own keytab (`host/<node>`), the certificate is requested via `ipacert` for principal `host/<node>`, and the issued PEM is written on the node

#### Scenario: Node client cert self-enrolled by the node
- **WHEN** a worker node needs its client certificate and it does not yet exist
- **THEN** the node generates its own private key and CSR locally, mints a ticket from its own host keytab into its own scratch cache, requests the certificate via `ipacert` as `host/<node>`, and the issued PEM is written on the node — no task generates the node's key or CSR on the master, and no task copies the node's private key to another host

#### Scenario: Control-plane component client certs use the master's host identity
- **WHEN** the master enrolls its front-proxy, controller-manager, or scheduler client certificates
- **THEN** the enrollment authenticates with a ticket minted on the master from the master's own host keytab for principal `host/<master>`

#### Scenario: Keytab absent or stale
- **WHEN** the `kubeclusteradm` keytab probe fails on the `kubeclusteradm` enrollment
- **THEN** the flow falls back to an admin ticket and the certificate is still issued

## ADDED Requirements

### Requirement: Realm admin password is confined to the control node and the IPA server
Tasks that authenticate to the FreeIPA API with realm-admin rights SHALL run delegated to the IPA server and authenticate with an `admin` scratch ticket (module-acquired, `env: KRB5CCNAME`), following the existing scratch-cache convention. No task targeting a Kubernetes master or worker host SHALL pass `ipaadmin_password` (or otherwise deliver the realm admin password to that host).

#### Scenario: No admin password on kube hosts
- **WHEN** the task files under `tasks/` are reviewed after the change
- **THEN** no task with a kube host as target (not delegated to the IPA server) references `ipaadmin_password`

#### Scenario: Admin API operation runs on idm with a scratch ticket
- **WHEN** a converge-time flow needs realm-admin rights against the FreeIPA API
- **THEN** the task is delegated to the IPA server, a pre-cleared `admin` scratch ticket under `/run/krb5cc` is acquired there, and the task inherits it via `env: KRB5CCNAME`
