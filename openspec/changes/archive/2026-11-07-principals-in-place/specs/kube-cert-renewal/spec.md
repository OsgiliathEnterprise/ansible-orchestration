# Spec Delta: kube-cert-renewal

## ADDED Requirements

### Requirement: Timer ticks authenticate into a unit-scoped credential cache
The `kube-cert-renew` service SHALL run with a unit-scoped Kerberos credential cache under its systemd `StateDirectory` (`/var/lib/kube-cert-renew/ccache` via `Environment=KRB5CCNAME`). The timer MUST NOT read or write the ambient root ticket cache (`/tmp/krb5cc_0`) or any cache under `/tmp`, and the keytab it authenticates with MUST NOT live under `/tmp`.

#### Scenario: Timer tick uses its own cache
- **WHEN** the weekly timer fires a renewal tick on a host
- **THEN** the tick's tickets are written to `/var/lib/kube-cert-renew/ccache` and no ticket file is created or modified under `/tmp`

#### Scenario: Stale unit cache cannot poison a tick
- **WHEN** a tick starts while an expired ticket remains in the unit-scoped cache
- **THEN** the script clears that cache before `kinit` and proceeds on a freshly minted ticket (or logs and skips the affected certificate)

#### Scenario: Keytab placement and mode
- **WHEN** renewal setup completes on the IPA server and on the master
- **THEN** the `kubeclusteradm` keytab exists at its unit-state location with mode `0600` and owned by root, and no `kubeclusteradm.keytab` remains under `/tmp`
