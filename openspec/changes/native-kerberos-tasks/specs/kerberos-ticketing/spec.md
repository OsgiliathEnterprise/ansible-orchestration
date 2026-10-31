## ADDED Requirements

### Requirement: Tickets are acquired fresh into a scratch cache
Ticket acquisition SHALL acquire a fresh ticket into a dedicated scratch cache path under `/tmp` (per purpose), preceded by a pre-clear of that path, and SHALL NOT rely on, or write to, the ambient per-user cache. Downstream consumers SHALL receive the cache via `env: KRB5CCNAME`.

#### Scenario: fresh converge, no cache present
- **WHEN** a ticketing task runs and no cache exists at the scratch path
- **THEN** the acquisition creates the cache and downstream consumers authenticate with it

#### Scenario: stale or expired cache present
- **WHEN** a ticketing task runs and a stale or expired ticket already exists at the scratch path
- **THEN** the cache is pre-cleared first and a fresh ticket is acquired — the stale ticket is never reused

#### Scenario: idempotent re-run
- **WHEN** a ticketing task re-runs on a host that already holds a valid ticket at the scratch path
- **THEN** the task reports no change (the scratch cache is ephemeral state, not configuration)

### Requirement: Keytab usability probes use a fresh acquisition
A keytab usability probe SHALL attempt a fresh ticket acquisition from the keytab into a scratch cache, within a block/rescue. A usable keytab mints a fresh ticket for the keytab's principal; a rotated keytab fails the probe. The probe SHALL NOT read or write the ambient cache, and SHALL report no change.

#### Scenario: keytab is usable
- **WHEN** the keytab holds a current key for its principal
- **THEN** the scratch cache holds a fresh ticket for the keytab's principal and the probe succeeds

#### Scenario: keytab is rotated (stale key)
- **WHEN** the keytab holds a stale key (rotated since its last export)
- **THEN** the fresh acquisition fails (the KDC rejects the old key), the probe reports the keytab unusable, and the flow falls through to the password fallback

#### Scenario: no ambient dependency
- **WHEN** the probe runs on a host whose ambient cache holds a ticket for a different principal
- **THEN** the probe outcome depends only on the keytab, not on the ambient cache

### Requirement: Keytab export uses the native module with forced replacement
The `kubeclusteradm` keytab export SHALL use `community.general.ipa_getkeytab` with an LDAP bind (`bind_dn`/`bind_pw`) and `force: true`. The export SHALL NOT require a Kerberos ticket, and an existing keytab file SHALL be replaced (delete + recreate), never appended to.

#### Scenario: export without a ticket
- **WHEN** the keytab export runs on a host with no Kerberos ticket at all
- **THEN** the export succeeds via the LDAP bind

#### Scenario: existing keytab is replaced, not appended
- **WHEN** the keytab file already exists, with or without a stale entry for the same principal
- **THEN** the file is recreated with the current entry — append-shadowing is impossible

#### Scenario: rotation block skipped in steady state
- **WHEN** the keytab exists and is usable
- **THEN** the rotation block does not run and the flow reports no change

#### Scenario: rotation replaces the keytab
- **WHEN** the keytab is absent or unusable
- **THEN** the rotation block runs, the file is recreated via the native module, and the task reports a change
