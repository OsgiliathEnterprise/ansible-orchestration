# Proposal

## Why

systemd-resolved on IPA infrastructure hosts currently lists local bind and a public resolver (8.8.8.8) as *unscoped* default servers, so private-domain queries — including zone SOA lookups during IPA SAN validation (`ipalib/certtools _validate_san_ips`) — race between bind and the public resolver; the public NXDOMAIN wins and IP-SAN certificate requests fail. Today this is papered over by `tcharl.ansible_orchestration` rewriting `/etc/systemd/resolved.conf.d/head.conf` on idm mid-converge (evicting 8.8.8.8 entirely): a second writer clobbers `tcharl.freeipa_server`'s file, and cert-renewal setup is coupled to resolver configuration it does not own.

## What Changes

- `tcharl.freeipa_server`: its `head.j2` resolved drop-in becomes a scoped dual-nameserver config — local bind scoped to the company domain plus its reverse zone, 8.8.8.8 kept as unscoped default (both nameservers retained).
- New var `freeipa_server_additional_dns_cidr` (default: this host's /24) drives the reverse-zone scoping; no assumption about a specific private range (10/8, 192.168/x, etc.).
- `tcharl.ansible_securehost`: same scoped pattern for client hosts, driven by new var `securehost_additional_dns_cidr` (default: the client's own /24).
- `tcharl.ansible_orchestration`: remove the head.conf override snippet from `tasks/ipa-cert-renewal.yml`; renewal no longer manages resolver configuration — the SAN-validation precondition is satisfied by infrastructure roles during prepare instead.

## Capabilities

### New Capabilities

- `resolved-dns-scoping`: scoped dual-nameserver systemd-resolved configuration on IPA server and client hosts — the private forward domain and its reverse zone resolve via local bind only; a public resolver remains the unscoped default for everything else (internet + public reverse lookups).

### Modified Capabilities

- `kube-cert-renewal`: adds a requirement that SAN-validation DNS preconditions are owned by infrastructure roles (`tcharl.freeipa_server` / `tcharl.ansible_securehost` scoped config) — renewal tasks SHALL NOT write `/etc/systemd/resolved.conf.d`.

## Impact

- **tcharl.freeipa_server** (shared role, included by ~15 molecule scenarios + `osgiliath-configure.yml`): `defaults/main.yml` (+1 var), `templates/systemd-resolved.conf.d/head.j2` (scoped content). All consuming scenarios get the scoped behavior.
- **tcharl.ansible_securehost**: same two-file pattern for client hosts (`defaults/main.yml`, `templates/systemd-resolved.conf.d/head.j2`).
- **tcharl.ansible_orchestration**: `tasks/ipa-cert-renewal.yml` loses the head.conf copy + restart tasks; no other renewal logic changes.
- Runtime behavior: idm and clients keep both nameservers; private-domain queries stop leaking to the public resolver; internet resolution is unchanged (8.8.8.8 default).
- Verification requires a live converge cycle (`resolvectl status` on idm + clients, IP-SAN cert-request, verify suite) — the environment must be rebuilt first.
