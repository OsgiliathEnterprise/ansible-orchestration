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

### Requirement: Keytab export is non-rotating, replace-not-append, master-local
The `kubeclusteradm` keytab export SHALL write the **current KDB key without rotating it**, using the only mechanism that can on this FreeIPA build: `kadmin.local ktadd -norandkey` executed on the IPA master (documented shell exception — the native `community.general.ipa_getkeytab` has no non-rotating path there: `retrieve_mode`/`--retrieve` is refused because `krbPrincipalKey` is search-ACI-protected, and its default mode rotates; see design D3 amendment). The export SHALL take no ticket, keytab, bind DN, or password in task parameters (`kadmin.local` binds to the local KDB). The existing keytab file SHALL be replaced — declaratively deleted, then exported — never appended to. The principal key SHALL be unchanged by re-export, the managed password SHALL NOT be invalidated by keytab regeneration, and the keytab SHALL track the KDB across re-exports.

#### Scenario: existing keytab is replaced, not appended
- **WHEN** the keytab file already exists, with or without a stale entry for the same principal
- **THEN** the file is deleted and re-exported with the current entry — append-shadowing is impossible

#### Scenario: export needs no credential material in parameters
- **WHEN** the export runs
- **THEN** it succeeds via the master-local KDB bind, without an ambient or scratch ticket, and without a bind DN or password in task parameters

#### Scenario: re-export does not invalidate the managed password
- **WHEN** the rotation block runs the export twice in a row (keytab unusable, then forced regeneration)
- **THEN** the `kubeclusteradm` managed password remains usable after both exports (`-norandkey` did not rotate the key), and the keytab authenticates on both runs

#### Scenario: external KDB key change is picked up by the next regeneration
- **WHEN** the KDB key for `kubeclusteradm` changes externally, and the rotation block runs
- **THEN** the keytab probe fails (keytab key no longer matches the KDB), the export runs, and the new keytab holds the current key — written, not rotated

#### Scenario: rotation block skipped in steady state
- **WHEN** the keytab exists and is usable
- **THEN** the rotation block does not run and the flow reports no change

#### Scenario: rotation replaces the keytab
- **WHEN** the keytab is absent or unusable
- **THEN** the rotation block runs, the file is recreated (delete + `ktadd -norandkey`), and the task reports a change

### Requirement: CA #2 client-certificate enrollments authenticate with a scratch ticket
The CA #2 client-certificate enrollments (`tasks/kube-node-cert.yml`, `tasks/admin-user.yml`) SHALL NOT pass `ipaadmin_password` to `freeipa.ansible_freeipa.ipacert`. The module SHALL run delegated to the IPA master, where it consumes a scratch cache minted by `community.general.krb_ticket` via `environment: KRB5CCNAME` (the module's `ipa_connect` honors the env-var cache and requires no password parameter). The CSR and issued certificate SHALL be shuttled between the control plane and the master by in-memory copy (`slurp` + `copy: content:`), and staged temp files on the master SHALL be cleaned up. The enrollment identity follows the `main.yml` ordering:

- **Node client cert** (`kube-node-cert.yml`) runs before `ipa-kube-admin-credential.yml`, so the `kubeclusteradm` user and keytab do not exist yet — it SHALL mint an **admin** password ticket (same convention as `ipa-cert-renewal.yml` / `kube-install-join-node.yml`). A non-privileged identity cannot enroll a `host/...` principal at all (VM-verified: "Insufficient access: not allowed to perform operation: request certificate" — requesting on behalf of another principal requires admin/CA-agent rights), so this is a policy necessity, not a convenience.
- **Admin client cert** (`admin-user.yml`) runs after `ipa-kube-admin-credential.yml` exported the keytab, so it SHALL mint the **`kubeclusteradm` keytab** ticket (self-request is permitted: CA ACL `user category: all` and a non-empty host-principal list does not constrain user principals — VM-verified: self-request issued), falling back via block/rescue to an admin password ticket when the keytab is missing or rotated.

#### Scenario: fresh converge node-cert enrollment
- **WHEN** a node has no local client certificate and enrollment runs
- **THEN** an admin scratch ticket is minted on the master (pre-cleared), `ipacert` authenticates via `KRB5CCNAME` with no password parameter, and the issued cert is shuttled back and installed on the node

#### Scenario: steady-state admin-cert enrollment is keytab-only
- **WHEN** the admin certificate is (re)enrolled and the `kubeclusteradm` keytab is usable
- **THEN** the ticket is minted from the keytab — no admin password touches the request

#### Scenario: keytab unusable at admin-cert enrollment
- **WHEN** the keytab mint fails (missing or rotated)
- **THEN** the rescue mints an admin password ticket and enrollment proceeds

#### Scenario: enrollment skipped when certificate already present
- **WHEN** a reconverge finds the node's (or master's) client certificate on disk
- **THEN** the ticketing, staging, enrollment, and shuttle tasks are all skipped (gated on the certificate stat), and the flow reports no change

### Requirement: Ticket tasks report no change
Ticketing tasks acquire ephemeral state (scratch caches), not persistent host state. Ticket tasks SHALL report `changed_when: false` (a ticket cache is ephemeral, in the same class as today's credential-cache renewal). The role's idempotence cycle (converge → reconverge) SHALL show no change from ticketing tasks in steady state.

#### Scenario: Steady-state ticketing reports no change
- **WHEN** the role runs a second consecutive converge in steady state
- **THEN** every ticketing task reports no change, and the role's idempotence check passes
