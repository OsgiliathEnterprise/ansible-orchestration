## 1. Test A — remove monkey patch, keep profile flag + /etc/hosts

- [x] 1.1 Remove the `patch IPA cert.py` task (L12-28) and its `ipactl restart` from `tasks/ipa-kubernetes-ca.yml`; leave the `disableDogtagReachabilityValidation=true` lineinfile (L176-185) and both `/etc/hosts` entries (L187-201) untouched
- [x] 1.2 Run a fresh-scenario cycle: `tox -e destroy --scenario-name=parallels` then `tox -e converge-monorepo --scenario-name=parallels`
  - `tox -e destroy` OK (252s); `tox -e converge-monorepo` **failed at the first `ipacert` task** (expected for Test A).
- [x] 1.3 Record the outcome of every `ipacert` task (`ipa-api-server.yml`, `kube-apiserver-kubelet-client.yml`) verbatim — pass, or the exact error message (predicted failure signature: "IP address in subjectAltName ... unreachable from DNS names" / "... does not have PTR record")
  - `Ipa-api-server | Check apiserver cert existence` (stat): `ok` — `{"exists": false}`
  - `Ipa-api-server | configure http service` (delegated to idm): `ok` — `changed: false`
  - `Ipa-api-server | create apiserver certs` (openssl_privatekey): `changed` — wrote `/etc/kubernetes/pki/apiserver.key`
  - `Ipa-api-server | create kube-apiserver csr` (openssl_csr): `changed` — wrote `/etc/kubernetes/pki/apiserver.csr`
  - **`Ipa-api-server | request apiserver certificate from IPA` (ipacert): FAILED** — verbatim: `"cert_request: -----BEGIN CERTIFICATE REQUEST-----\nMIIFDz…(CSR body)…-----END CERTIFICATE REQUEST-----\n: invalid 'csr': IP address in subjectAltName (10.96.0.1) unreachable from DNS names"` — **exactly the predicted FreeIPA-layer signature** (H1 confirmed false: the profile flag + `/etc/hosts` entries do not affect `_validate_san_ips`).
  - `Kube-apiserver-kubelet-client | *` (including the second `ipacert` task): **not executed** — play aborted at the first `ipacert` failure. PLAY RECAP: `master.osgiliath.test: ok=212 changed=73 failed=1`.
- [x] 1.4 Decision gate D3a: if all ipacert tasks succeed and issued certs carry the expected SANs → keep L12-28 removed, add a comment on the profile-flag task stating it covers only the Dogtag layer while the FreeIPA-layer check is satisfied by (record how), and proceed to section 4. If any ipacert task fails with the predicted signature → restore L12-28 and proceed to Test B
  - **Outcome: FAIL path taken.** `ipacert` failed with the predicted signature → L12-28 (patch + `ipactl restart`) restored verbatim; proceeding to Test B (section 2).

## 2. Test B — satisfy `_validate_san_ips` via IPA zone records (only if Test A failed)

- [x] 2.1 Identify every IP SAN used by `ipacert` CSRs in this role (master node IP, service cluster IP; check `kube-install.yml` certSANs and the CSR generation tasks)
  - Only `apiserver.csr` (`tasks/ipa-api-server.yml:38-46`) carries IP SANs: `10.96.0.1` (first usable of `kube_service_cidr` default `10.96.0.0/12`) and `10.211.55.11` (`orchestration_master_ip` — master private-network interface, static per `molecule/parallels/molecule.yml`). `apiserver-kubelet-client.csr`, `front-proxy-client.csr`, `kubeadm.csr` (admin-user) carry no SANs (CN only); `delete-ipa-cleanup.yml` / `ipa-admin-cert.yml` are delete-path/orphan, not in the converge graph. `kube-install.yml:109` kubeadm `certSANs` mirror the same IP set.
- [x] 2.2 Add IPA-managed DNS records so each SAN IP is reachable from a DNS name present in the same SAN: A record(s) for an alias name → IP, plus matching PTR record (verify with `ipa dnsrecord-find`)
  - Added to `tasks/ipa-kubernetes-ca.yml` (after the `/etc/hosts` entries): `ipadnszone` ensure-reverse-zone for the service-cluster and master-IP /24s, `ipadnsrecord` A `kubernetes-svc.{{ company_domain }}` → service cluster IP and A `kubernetes-master.{{ company_domain }}` → `orchestration_master_ip`, plus matching PTR records (`1.0.96.10`, `11.55.211.10`) pointing at the aliases.
- [x] 2.3 Extend the relevant `certSANs` list with the alias name(s) added in 2.2 so forward reachability holds within the SAN set
  - `tasks/ipa-api-server.yml` CSR `subject_alt_name` now includes `DNS:kubernetes-svc.{{ company_domain }}` and `DNS:kubernetes-master.{{ company_domain }}` alongside the existing DNS/IP entries.
- [x] 2.4 Fresh-scenario cycle (`tox -e destroy` + `converge-monorepo`) without the monkey patch; verify all ipacert tasks succeed and inspect the issued API server cert's SAN set (original IPs present, added names present)
  - Fresh environment: `tox -e destroy` OK (204s). First fresh converge failed at the apiserver `ipacert` task with a new signature: `PTR record for SAN IP (10.211.55.207) does not match A/AAAA records` — the master zone (and the back-filled `207 → master` record) is created during the *prepare* phase (host enrollment auto-creates the reverse zone), so a reset gated on zone-creation was skipped (zone task `changed: false`).
  - **Design fix**: replaced the non-idempotent `del_all` resets with a *targeted* removal — `state: absent` + `record_type: PTR` + `record_value: [{{ orchestration_host_hostname.split('.')[0] }}]` (only the back-filled shortname; no-op when absent, hence idempotent). The service-zone reset was removed entirely (non-host IPs are never back-filled). The removal runs between the two PTR creates.
  - Re-converge in the same fresh environment: `converge-monorepo` OK (419s), all ipacert tasks (apiserver, front-proxy, kubelet-client) succeeded.
  - Issued cert SAN set (master, `openssl x509 -in /etc/kubernetes/pki/apiserver.crt`): `DNS:master.osgiliath.test, DNS:kubernetes-svc.osgiliath.test, DNS:kubernetes-master.osgiliath.test, IP Address:10.96.0.1, IP Address:10.211.55.207` — original IPs present, added alias names present; issuer `CN=kubernetes-ca` (IPA CA), subject `CN=master.osgiliath.test, O=system:masters`.
- [x] 2.5 Decision gate D3b: if Test B passes → keep zone records + certSANs, document them as load-bearing (removing breaks issuance), confirm L12-28 stays removed; if it fails → restore the monkey patch and proceed to section 3
  - **PASS path taken.** Test B passed without the monkey patch. Landed state: `ipadnszone` ensure for both reverse /24s, `ipadnsrecord` A + PTR for both aliases, targeted shortname removal for the master IP; CSR SAN extension in `ipa-api-server.yml`. Documented as load-bearing in the `tasks/ipa-kubernetes-ca.yml` comment block (removing breaks issuance with the FreeIPA-layer signature). The `patch IPA cert.py` + `ipactl restart` tasks (old L12-28) remain removed — no monkey patch in the tree. Section 3 not needed.

## 3. Hardened fallback — keep and harden the monkey patch (only if both tests failed)

_Not needed — Test B (section 2) passed, so the monkey patch stays removed. 3.1-3.3 not performed._

## 4. Final verification of the landed state

- [x] 4.1 Fresh-scenario converge succeeds end-to-end (`tox -e destroy` + `converge-monorepo`)
  - `tox -e destroy` OK (204s) → fresh converge OK (419s, `congratulations :)`), zero fatals. `verify-monorepo` OK (95s) on the same fresh environment.
- [x] 4.2 Idempotence check: second converge reports no changes in `ipa-kubernetes-ca.yml` tasks (no re-patch, no spurious `ipactl restart`, no duplicate zone records)
  - Second consecutive converge OK (535s). All seven DNS tasks (`ensure reverse zone` x2, `create A record` x2, `create PTR record` x2, `remove back-filled host shortname`) report `ok` / `changed: false` — the targeted shortname removal is a no-op when the value is absent, so the section is fully idempotent. No patch tasks exist to re-run; no `ipactl restart` in the graph.
- [x] 4.3 Update the task comments so each surviving mitigation states which layer it covers; confirm no dead mitigation remains
  - Landed mitigations and their layers: (1) `disableDogtagReachabilityValidation=true` profile flag + (2) `/etc/hosts` entries on the idm → **Dogtag layer** (task names state this); (3) IPA zone/A/PTR records + CSR alias names + targeted shortname removal → **FreeIPA layer** (`_validate_san_ips`, documented in the comment block above the zone tasks, which also states the records are load-bearing and that the profile flag/`/etc/hosts` entries do not affect the FreeIPA-layer check). No monkey-patch tasks remain; no dead mitigation.
