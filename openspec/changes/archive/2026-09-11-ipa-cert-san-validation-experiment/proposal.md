## Why

`tasks/ipa-kubernetes-ca.yml` stacks three mitigations against one problem — certificate requests whose CSRs carry IP SANs (kubeadm `certSANs`: master node IP + service cluster IP) failing reachability validation:

1. **Monkey patch** (L12-28): a `sed -i` into FreeIPA's installed `ipaserver/plugins/cert.py` injecting an early `return` into `_validate_san_ips()`, plus a full `ipactl restart`. Fragile: hardcodes the Python version path (`/usr/lib/python3.14/site-packages`), rewrites vendor site-packages (lost on any FreeIPA package upgrade; the `.bak` backup is never restored), and restarts all IPA services on every fresh install.
2. **Profile flag** (L176-185): `disableDogtagReachabilityValidation=true` in the `kubeAdministrators` profile — controls the *Dogtag/PKI* layer's reachability check.
3. **/etc/hosts entries** (L187-201): map the service cluster IP and master IP to the hostname on the IPA server, for "Dogtag reachability check".

Source analysis of FreeIPA `cert.py` (`cert_request.execute`) shows these target *different layers*: `_validate_san_ips()` is an unconditional **FreeIPA-layer** check (runs before Dogtag sees the request; requires each SAN IP to be reachable from a SAN DNS name via IPA-managed A/AAAA records with matching PTR — no profile parameter controls it), while `disableDogtagReachabilityValidation` governs only the downstream **Dogtag layer**. The necessity of each mitigation is therefore unverified — they were likely stacked because the author was unsure which one actually does the work.

## What Changes

An experiment (per user decision: "experiment in a dedicated change") to determine empirically which mitigations are necessary, with a decision gate that lands on one of two outcomes:

- **Test A** — remove only the monkey patch (keep profile flag + /etc/hosts), run a fresh-scenario converge. Source analysis predicts failure at the FreeIPA layer ("IP address in subjectAltName unreachable from DNS names" / "does not have PTR record"), which would confirm H1 false and keep the patch.
- **Test B** — if Test A fails as predicted, evaluate the cleaner alternative: *satisfy* `_validate_san_ips` instead of disabling it — add IPA-managed DNS records (A + PTR) so each SAN IP resolves through a SAN DNS name, then remove the monkey patch. If this works, it eliminates the site-packages hack entirely at the cost of extra SAN entries and zone records.
- **Outcome gate** — whichever test succeeds defines the final state: keep-and-document the patch (plus harden its path resolution) or replace it with DNS-satisfaction. The losing mitigation(s) are removed; the winner is documented with a comment explaining which layer it covers.

No spec delta: all specced behavior ("certificates SHALL be requested from `kubernetes-ca` via `ipacert`") is preserved under either outcome — this change alters *how* validation passes, not *what* gets issued.

## Capabilities

### New Capabilities

(None.)

### Modified Capabilities

(None — see proposal; both outcomes preserve all specced certificate-issuance behavior.)

## Impact

- `tasks/ipa-kubernetes-ca.yml` — the monkey-patch task (L12-28) is removed in Test A and restored or replaced depending on outcome; possible addition of IPA DNS record tasks (Test B path).
- Experiment requires fresh-scenario converge runs (`tox -e destroy` + `converge-monorepo`) per test — budget 5-15 min each.
- If Test B wins: new IPA zone records for the SAN IPs and an extra certSAN entry; if it loses: the monkey patch stays but gains a dynamic module-path resolution (no hardcoded Python version) and a comment documenting both validation layers.
