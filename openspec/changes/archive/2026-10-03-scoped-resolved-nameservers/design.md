# Design

## Context

See proposal.md for motivation. Current state that shapes this design:

- `tcharl.freeipa_server` deploys `/etc/systemd/resolved.conf.d/head.conf` on idm during prepare (`tasks/post-install.yml`): `DNS=<bind-ip> 8.8.8.8` + `Domains=~<company_domain>` — both servers **unscoped defaults**, so private-domain queries (incl. zone SOA lookups) race between bind and the public resolver.
- `tcharl.ansible_securehost` deploys the same unscoped pattern on clients (`tasks/freeipa-client.yml`, `dns_master_ip_to_set: securehost_idm_ip`).
- `tcharl.ansible_orchestration/tasks/ipa-cert-renewal.yml` overwrites idm's head.conf mid-converge with a bind-only config (evicting 8.8.8.8) because IPA SAN validation (`ipalib/certtools _validate_san_ips`) discovers IP-SAN zones through the system resolver and fails when the public NXDOMAIN wins that race.
- systemd-resolved semantics: unscoped `DNS=` entries are default servers for everything; a following `Domains=<domain>` (no prefix) scopes those servers to that domain; `~<domain>` marks a routing/search-list domain only.
- The change spans three sibling role repos; the change record lives in orchestration's openspec home because it is the integration role consuming both.

## Goals / Non-Goals

**Goals:**
- Scoped dual-nameserver resolved config on idm and clients: bind scoped to company domain + private reverse zone, 8.8.8.8 kept as unscoped default — both nameservers retained everywhere.
- Reverse-zone scoping driven by a per-role CIDR variable (no assumption about any specific private range).
- Orchestration renewal flow stops managing resolver configuration; the SAN-validation precondition is owned by infrastructure roles during prepare.

**Non-Goals:**
- `tcharl.ansible_nameserver`'s orphaned `head.j2` template + handler — dead code, separate cleanup (that role manages IPA DNS records, not resolved config).
- Per-link/networkd-level resolved configuration; global drop-in only.
- IPv6 reverse scoping (`ip6.arpa`) — lab is IPv4-only.
- Multi-CIDR list support — single CIDR variable today (see Decisions D5).

## Decisions

**D1: Scope instead of evict or reorder.** Alternatives considered: (a) keep both servers unscoped and rely on ordering — rejected, resolved's selection among default servers is not a reliable priority; the observed failure is exactly this race. (b) Evict the public resolver (today's orchestration workaround) — rejected per requirement to keep both nameservers; idm/clients lose internet fallback. Chosen: scope bind to `company_domain` + its reverse zone, leave 8.8.8.8 unscoped — deterministic routing per query class, no race by construction.

**D2: Fix at the source roles, delete the consumer override.** head.conf on idm is owned by freeipa_server (prepare) and on clients by securehost; the scoped config belongs in their templates. Orchestration's mid-converge overwrite becomes a second writer with layering inversion and is deleted. Alternative — keep an orchestration-side override carrying the scoped content — rejected: clobber-order dependency and duplicated knowledge of resolver layout.

**D3: Reverse-zone scoping via CIDR variable, pure-Jinja zone math.** New vars `freeipa_server_additional_dns_cidr` (default: host's own /24) and `securehost_additional_dns_cidr` (default: client's own /24), defined in each role's `defaults/main.yml` as lazy-evaluated Jinja over the role's existing IP fact (`freeipa_server_exposed_ip`, `securehost_currenthost_ip`) — both roles run facts before the deploying task, so resolution is safe. Zone name computed by octet reversal mirroring the existing nameserver-role pattern (`split('.')[:prefix//8][::-1]` + `.in-addr.arpa`) — no new collection dependency; `ansible.utils.ipsubnet` (already declared in both roles) only computes the /24 default. Constraint: octet-aligned prefixes (/8, /16, /24), same as the existing nameserver role. Alternatives rejected: scoping all of `in-addr.arpa`/`ip6.arpa` to bind (public reverse lookups would hit bind and get NXDOMAIN); hardcoding a 10/8 assumption.

**D4: Keep the `~<domain>` routing entry.** The current config's `Domains=~{{ domain }}` provides search-list behavior for unqualified names; the scoped line keeps both forms (`<domain> ~<domain>`) so that behavior is preserved, not silently dropped.

**D5: Single CIDR string, not a list.** Matches the variable naming and all current scenarios (parallels/kvm/default put idm + cluster in one /24, so the default covers every host). Multi-subnet deployments override per scenario; extending to a list is a trivial follow-up if ever needed.

**D6: Cross-repo coordination.** One change record in orchestration's openspec home (planning root); implementation edits land as separate commits in each of the three role repos, following per-repo conventions. Monorepo scenarios resolve sibling roles from local paths, so a single converge picks up all three consistently; standalone consumers pull unpinned Galaxy versions and need the re-published roles (see Migration Plan).

## Risks / Trade-offs

- [Mixed `Domains=<domain> ~<domain> <zone>` line semantics unverified] → first verification step is `resolvectl status` on idm + a client; if resolved parses the mixed line differently than expected, split into separate `DNS=`/`Domains=` lines (fallback shape known in advance).
- [SAN validation may query reverse zones outside the scoped /24 (multi-subnet clusters)] → default covers single-subnet scenarios; multi-subnet override is documented; end-to-end proof = IP-SAN cert-request with no "unreachable" warnings.
- [Blast radius: ~15 molecule scenarios + `osgiliath-configure.yml` consume freeipa_server] → approved by user; scoped behavior is strictly more correct (private queries stop leaking to the public resolver) and each role's own molecule suite runs in CI.
- [Lazy-evaluated default referencing a fact set later in the play] → verified import order in both roles (`facts.yml` before `post-install.yml` / `freeipa-client.yml`); same pattern as existing `dns_master_ip_to_set` usage.
- [Environment is currently destroyed — no live verification until rebuild] → tasks include a full create/prepare/converge cycle with `resolvectl` assertions and the verify suite before any task is marked done.

## Migration Plan

1. **freeipa_server**: add var + scoped template (independent, deployable alone).
2. **securehost**: same pattern for clients (independent of 1).
3. **orchestration**: delete the head.conf override snippet from `tasks/ipa-cert-renewal.yml` — must be live in a converged environment only after steps 1+2, otherwise idm reverts to unscoped dual defaults and SAN validation regresses. In monorepo checkouts all three are consumed from local paths, so one converge applies everything atomically; standalone consumers need the re-published freeipa_server + securehost (requirements-standalone.yml pins no versions).
4. **Rollback**: revert each template to its previous content; head.conf is fully managed and converges back on the next run — no manual cleanup needed.

## Open Questions

- Whether the `~<domain>` routing entry is strictly required (i.e., whether anything on idm/clients relies on unqualified-name resolution). Deferrable: verify empirically during the live cycle; dropping it would not change specs, approach, or task breakdown.

## Update (post-implementation)

Implementation revealed that `resolved.conf.d` drop-ins **cannot express per-server domain scoping**: a `DNS=` value must parse word-by-word as addresses (`manager_parse_dns_server_string_and_warn()`), so inline `Domains=` tokens after server addresses are silently dropped with journal warnings, and true "server X only for domain Y" requires networkd `.network` files or D-Bus. The committed templates therefore use the only valid shape achieving the intent — separate lines:

```ini
[Resolve]
DNS=<bind>          # listed first = preferred global server
DNS=8.8.8.8        # fallback
Domains=~<domain> ~<reversed-zone>.in-addr.arpa   # route-only entries
```

Consequences vs the original plan: (1) D1's "scope bind, leave 8.8.8.8 unscoped" becomes global server-ordering preference + route-only domains — private lookups prefer bind by first-listed ordering, public resolution falls back to 8.8.8.8; strict per-domain isolation is not guaranteed (accepted trade-off, identical semantics to the previously working configuration). (2) Variable names are `freeipa_server_idm_dns_cidr` / `securehost_idm_dns_cidr` (not `*_additional_dns_cidr`); securehost's default derives from `securehost_idm_ip`'s /24. (3) Specs and task descriptions were updated to match; the empirical routing behavior remains a live-cycle verification step (task 4.3). Source-verified analysis: `tcharl.ansible_securehost/openspec/changes/archive/2026-09-30-fix-resolved-domain-routing/`.
