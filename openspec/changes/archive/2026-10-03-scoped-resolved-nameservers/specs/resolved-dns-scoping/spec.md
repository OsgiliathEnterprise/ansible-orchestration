# Spec Delta

## Purpose

Defines how systemd-resolved is configured on IPA infrastructure hosts so private DNS resolution prefers the authoritative bind server while public resolution keeps a fallback — a dual-nameserver setup where both nameservers are retained and the private namespaces (company domain + declared reverse zone) carry route-only entries. `resolved.conf.d` drop-ins cannot express per-server domain scoping, so routing is achieved through global server ordering preference plus route-only domains.

## ADDED Requirements

### Requirement: Dual-nameserver configuration with route-only private domains
The system SHALL configure systemd-resolved on the IPA server host and every IPA client host with exactly two nameservers — the local bind (IPA-DNS) server listed first as the preferred global server, and a public resolver as fallback — plus route-only (`~`) domain entries for the company domain and its reverse zone. Both nameservers SHALL be present — neither is evicted in favor of the other.

#### Scenario: Server host resolved state after prepare
- **WHEN** the IPA server role has converged on the idm host
- **THEN** `resolvectl status` lists both the local bind IP and the public resolver as global servers, with the bind listed first
- **AND** the global DNS Domain list carries route-only entries for the company domain (`~<company_domain>`) and the reverse zone of the declared private network (`~<reversed-zone>.in-addr.arpa`)

#### Scenario: Client host resolved state after prepare
- **WHEN** the securehost role has converged on an IPA client host
- **THEN** `resolvectl status` lists both the idm bind IP and the public resolver with the same pattern as the server host, using the declared private network for the reverse zone

### Requirement: Private-domain queries prefer local bind
Queries for the company domain and its subdomains SHALL be routed to the preferred (local bind) server; lookups in the declared private reverse zone SHALL likewise prefer the local bind server. Routing is best-effort by server ordering plus route-only domains — strict per-server isolation is not expressible in `resolved.conf.d` drop-ins (would require networkd `.network` files or D-Bus). The company domain's route-only entry SHALL preserve unqualified-name resolution behavior against it, matching the previously working configuration.

#### Scenario: FQDN lookup stays local
- **WHEN** any configured host resolves `<name>.<company_domain>`
- **THEN** the query is answered by the preferred (local bind) server rather than failing over to the public resolver

#### Scenario: Unqualified name resolution preserved
- **WHEN** a process on a configured host resolves an unqualified hostname
- **THEN** resolution against the company domain succeeds through the local bind server, matching the previously working configuration's behavior

### Requirement: Private reverse-zone queries prefer local bind
Reverse lookups for the private network declared per host SHALL be routed to the preferred (local bind) server, which serves the /24 reverse zones. The declared network SHALL default to a /24 derived from the role's IP fact and SHALL be overridable per scenario via `freeipa_server_idm_dns_cidr` (server role) or `securehost_idm_dns_cidr` (client role).

#### Scenario: Private IP reverse lookup stays local
- **WHEN** a configured host performs a reverse lookup for an IP within its declared private network
- **THEN** the query is answered by the preferred (local bind) server rather than failing over to the public resolver

#### Scenario: Override changes the scoped zone
- **WHEN** a scenario overrides the CIDR variable with a different octet-aligned network
- **THEN** the route-only reverse zone matches that network's reversed prefix and resolution of its IPs still prefers bind

### Requirement: Public resolution keeps its fallback
Queries outside the private namespaces SHALL fall through to the public resolver as the second-listed global server. Internet name resolution and public IP reverse lookups MUST NOT be affected by the route-only domain entries.

#### Scenario: Public hostname resolves via fallback
- **WHEN** a configured host resolves a public hostname (e.g., `example.com`)
- **THEN** the query is answered through the public resolver

#### Scenario: Public IP reverse lookup uses fallback
- **WHEN** a configured host performs a reverse lookup for an IP outside all declared private networks
- **THEN** the query goes to the public resolver, not bind

### Requirement: Configuration is idempotent and restart-gated
The resolved drop-in SHALL be deployed by the infrastructure roles during prepare (server role on the idm host, client role on clients) with content stable across re-runs. systemd-resolved SHALL only be restarted when the file content actually changed.

#### Scenario: Re-run without changes triggers no restart
- **WHEN** the role runs a second time and the rendered drop-in is unchanged
- **THEN** no resolved restart is triggered

#### Scenario: Variable change updates config once
- **WHEN** the CIDR variable or company domain changes between runs
- **THEN** the drop-in file is updated and systemd-resolved is restarted exactly once for that change
