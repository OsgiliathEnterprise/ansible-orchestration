# Kerberos Ticketing

## Purpose

Require all Kerberos ticket acquisition in the role to run on the Ansible control node's native negotiation (module-managed credentials, scratch caches, keytab probes) rather than shell `kinit`, so ticketing is idempotent by construction, never reuses a stale ambient cache, and no shell exception is needed for ticket acquisition.

## Requirements

### Requirement: Ticket acquisition uses native Ansible negotiation, not shell kinit
The role SHALL acquire every Kerberos ticket with `community.general.krb_ticket` into a dedicated scratch cache under `/tmp`, pre-cleared (`file: state: absent`) before acquisition. No task under `tasks/` SHALL invoke `kinit`, `klist`, or `kdestroy` via `shell`, and no flow SHALL depend on the ambient per-user ticket cache (`~/.k5.<user>`). The role's shell-exception list SHALL NOT contain a ticketing exception; the comment in `tasks/requirements.yml` SHALL state that ticket acquisition runs through native modules.

#### Scenario: Full converge without shell kinit
- **WHEN** the role converges end to end
- **THEN** `grep -rn "kinit\|klist\|kdestroy" tasks/` returns no matches, and every Kerberos-authenticated `ipa`/`ipa_getkeytab`/`ipacert` task ran with a module-acquired scratch cache exported via `env: KRB5CCNAME`

#### Scenario: Stale scratch cache cannot be reused
- **WHEN** a converge is re-run while a scratch cache from a previous run still exists
- **THEN** the pre-clear task removes it before acquisition, the fresh ticket is written to a clean cache, and no task can silently proceed on an expired ticket

### Requirement: Keytab usability is probed with a native keytab ticket
Flows that prefer a keytab credential (admin credential, admin user) SHALL probe keytab usability with `community.general.krb_ticket` (`keytab: true`) into a scratch cache inside a `block:`/`rescue:` — success sets the keytab-usable fact, failure sets it false and the `rescue:` selects the password fallback. No probe SHALL be a shell `kinit -kt`.

#### Scenario: Fresh install with no keytab yet
- **WHEN** the renewal keytab has not been exported yet
- **THEN** the keytab probe fails, the flow falls back to the admin-password ticket, and converge proceeds

#### Scenario: Steady state with a valid keytab
- **WHEN** the keytab exists and its key matches the KDB
- **THEN** the keytab probe succeeds and no admin password is ever sent to the KDC by that flow

#### Scenario: Rotated keytab falls back
- **WHEN** the keytab's key no longer matches the KDB
- **THEN** the probe fails with `KRB5KDC_ERR_PREAUTH_FAILED`, the flow falls back to the admin-password ticket, and converge proceeds

### Requirement: Certificate enrollment uses the native ipa module with a delegated scratch ticket
The role SHALL enroll and issue FreeIPA certificates with the native `freeipa.ansible_freeipa.ipacert` module (GSSAPI negotiation via `KRB5CCNAME`), not shell `ipa` calls and not the nonexistent `community.general.ipa_getcert`. Enrollment of a `kubeclusteradm`-principal CSR SHALL authenticate as `kubeclusteradm` (keytab ticket with password fallback); enrollment of CA or host service principals SHALL authenticate with an `admin` ticket. CSR and certificate files SHALL be shuttled between the master and the IPA server with `slurp` and `copy: content:` (module file params resolve on the delegated host).

#### Scenario: Node client cert via keytab
- **WHEN** a node needs its client certificate from the `kubeclusteradm` CA
- **THEN** a `krb_ticket` keytab task on idm produces the ticket cache, an `ipacert` task delegated to idm requests the certificate as `kubeclusteradm`, and the issued PEM is copied back to the master

#### Scenario: Keytab absent or stale
- **WHEN** the keytab probe fails on the `kubeclusteradm` enrollment
- **THEN** the flow falls back to an admin ticket and the certificate is still issued

### Requirement: Renewal flow exports a non-rotating keytab natively
The renewal flow SHALL export the `kubeclusteradm` keytab with a non-rotating keytab export (`community.general.ipa_getkeytab`, LDAP bind via `bind_dn`/`bind_pw`, `force: true`): replace-not-append, the principal key is not rotated (kvno stable across re-export), and the admin password remains valid. The export SHALL be idempotent (no ticket required) and no task in the flow SHALL shell out to `kinit` or `kadmin ktadd`.

#### Scenario: Re-converge re-exports without rotation
- **WHEN** the renewal flow runs on a converge where the keytab already exists
- **THEN** `ipa_getkeytab` re-writes the keytab, the principal kvno is unchanged, and the task reports `ok` without a ticket
