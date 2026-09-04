## Context

The problem: CSRs for Kubernetes control-plane certificates carry IP SANs (master node IP `10.211.55.11`, service cluster IP `10.96.0.1` — see `kube-install.yml` certSANs). Certificate requests through FreeIPA's `ipacert` module fail reachability validation at one or two layers, so the role currently stacks three mitigations (see proposal.md).

### Source analysis (FreeIPA master, `ipaserver/plugins/cert.py`)

In `cert_request.execute()`, after SAN parsing:

```python
if san_ipaddrs:
    _validate_san_ips(san_ipaddrs, san_dnsnames)   # FreeIPA layer — unconditional
...
result = self.Backend.ra.request_certificate(csr_pem, profile_id, ca_id, ...)  # Dogtag layer
```

`_validate_san_ips()` requires, for every IP in the SAN:
1. **Forward reachability**: at least one *DNS name also present in the same SAN* resolves (via IPA-managed A/AAAA records, single CNAME max) to that IP.
2. **PTR record**: an IPA-managed PTR record exists for the IP.
3. **Loop consistency**: the PTR value appears among the names resolving to that IP.

Key facts:
- The check is **unconditional** — no profile parameter, flag, or config option disables it. It runs before `request_certificate` reaches Dogtag.
- All DNS lookups go through `api.Command['dnsrecord_show']` — i.e. only records in **IPA's own zones** count. `/etc/hosts` entries on the IPA server are invisible to this layer.
- `disableDogtagReachabilityValidation` does not appear anywhere in `cert.py`; it is a Dogtag/PKI profile parameter governing the CA's *own* reachability check (the downstream layer).

### Consequence

The three mitigations map to distinct layers:

| Mitigation | Layer addressed |
|---|---|
| Monkey patch (`_validate_san_ips` early-return) | FreeIPA layer — the only thing that disables it |
| `disableDogtagReachabilityValidation=true` | Dogtag layer only |
| `/etc/hosts` entries (10.96.0.1, master IP → hostname) | OS-level name resolution for whatever process does local reachability probing (likely Dogtag's); invisible to the FreeIPA layer |

**Hypothesis H1**: "the profile flag makes the monkey patch redundant" — predicted **false** by source analysis: removing the patch should fail at the FreeIPA layer regardless of the profile flag.

**Hypothesis H2**: instead of disabling, *satisfy* `_validate_san_ips` with IPA-managed DNS records — each SAN IP must be reachable from a SAN DNS name via zone A/AAAA + matching PTR. For `10.96.0.1` (virtual service IP) this requires a dedicated zone record whose name is also in the CSR's SAN set (e.g. add an A record for a k8s-service alias and include that name in `certSANs`).

## Goals / Non-Goals

**Goals:**
- Empirically determine which mitigations are necessary (Test A), and whether DNS-satisfaction (H2) is viable as a monkey-patch-free design (Test B).
- Land on one documented final state with the losing mitigation(s) removed.
- If the patch survives: harden it (dynamic module path, layer-documenting comment).

**Non-Goals:**
- No change to which certificates are issued or their subjects/SANs beyond what Test B may add (one extra SAN name on the API server cert — flagged for review if taken).
- No upstream FreeIPA patch/PR in this change (noted as future work).
- No spec delta (behavior preserved under both outcomes).

## Decisions

**D1: Test A is the first gate.** Remove only L12-28 (patch + restart), keep profile flag and /etc/hosts. Fresh-scenario converge; watch the `ipacert` tasks in `ipa-api-server.yml` / `kube-apiserver-kubelet-client.yml`.
*Pass criteria:* all ipacert requests succeed, issued certs carry expected SANs. *Fail signature (predicted):* "IP address in subjectAltName ... unreachable from DNS names" or "... does not have PTR record".

**D2: Test B only if D1 fails as predicted.** Add IPA zone records satisfying `_validate_san_ips` for each SAN IP, extend `certSANs` with the alias name(s) needed for forward reachability, remove the monkey patch.
*Pass criteria:* converge succeeds without the patch; issued API server cert contains the expected SAN set (original IPs + any added names).

**D3: Outcome gate.**
- D1 passes → delete L12-28 permanently; keep profile flag + /etc/hosts with a comment stating which layer each covers.
- D1 fails, D2 passes → adopt DNS-satisfaction; remove L12-28; document the zone records as load-bearing (removing them breaks cert issuance).
- Both fail → restore L12-28 and harden it: resolve `cert.py` via `python3 -c 'import ipaserver.plugins.cert, os; print(os.path.dirname(ipaserver.plugins.cert.__file__))'` instead of the hardcoded `/usr/lib/python3.14/...` path; add a comment documenting both validation layers and why each mitigation exists.

**D4: Fresh-scenario runs for every test.** The patch is applied conditionally (`grep -q "# Patched:"` guard) and IPA services are restarted, so in-place re-runs cannot cleanly simulate "patch absent" — `tox -e destroy` + recreate between tests is required to avoid stale patched state.

## Risks / Trade-offs

- [Test B changes the API server cert's SAN set] → Extra DNS-name SANs are additive and harmless to k8s (clients match by IP or existing names); flagged for review before adoption; rollback = drop the added `certSANs` entry + zone records.
- [Zone records for a virtual IP (10.96.0.1) look odd in DNS] → They are load-bearing validation artifacts, not routing hints; documented as such at creation time.
- [Experiment cost: 2-3 full converge cycles (~5-15 min each)] → Accepted; this is the price of replacing guesswork with evidence before touching a fragile site-packages hack.
- [FreeIPA version drift between source analysis and installed 4.x] → The `_validate_san_ips` call site was verified against current master; Test A's observed error message is the ground truth regardless.

## Migration Plan

1. Run Test A (destroy → converge with L12-28 removed) — record ipacert task outcomes verbatim.
2. If failed: run Test B (add zone records + certSANs, no patch).
3. Apply D3 outcome; remove losing mitigation(s); add layer-documenting comments to the survivors.
4. Final fresh-scenario converge + idempotence check on the landed state.

Rollback at any point = `git restore tasks/ipa-kubernetes-ca.yml` (+ revert zone records via `ipa dnsrecord-del` if Test B was applied).

## Open Questions

- Does Dogtag's reachability check actually consult `/etc/hosts` (i.e. are L187-201 load-bearing at all)? Test A isolates the FreeIPA layer; a follow-up micro-test (remove /etc/hosts entries with patch present) could settle this, but it is not required for the outcome gate — those entries are cheap and harmless to keep.
- Whether an upstream FreeIPA option (e.g. a future `--skip-san-ip-validation`) exists or is planned — out of scope; noted as future work if the patch survives.
