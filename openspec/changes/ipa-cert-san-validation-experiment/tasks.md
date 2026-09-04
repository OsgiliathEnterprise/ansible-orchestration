## 1. Test A — remove monkey patch, keep profile flag + /etc/hosts

- [ ] 1.1 Remove the `patch IPA cert.py` task (L12-28) and its `ipactl restart` from `tasks/ipa-kubernetes-ca.yml`; leave the `disableDogtagReachabilityValidation=true` lineinfile (L176-185) and both `/etc/hosts` entries (L187-201) untouched
- [ ] 1.2 Run a fresh-scenario cycle: `tox -e destroy --scenario-name=parallels` then `tox -e converge-monorepo --scenario-name=parallels`
- [ ] 1.3 Record the outcome of every `ipacert` task (`ipa-api-server.yml`, `kube-apiserver-kubelet-client.yml`) verbatim — pass, or the exact error message (predicted failure signature: "IP address in subjectAltName ... unreachable from DNS names" / "... does not have PTR record")
- [ ] 1.4 Decision gate D3a: if all ipacert tasks succeed and issued certs carry the expected SANs → keep L12-28 removed, add a comment on the profile-flag task stating it covers only the Dogtag layer while the FreeIPA-layer check is satisfied by (record how), and proceed to section 4. If any ipacert task fails with the predicted signature → restore L12-28 and proceed to Test B

## 2. Test B — satisfy `_validate_san_ips` via IPA zone records (only if Test A failed)

- [ ] 2.1 Identify every IP SAN used by `ipacert` CSRs in this role (master node IP, service cluster IP; check `kube-install.yml` certSANs and the CSR generation tasks)
- [ ] 2.2 Add IPA-managed DNS records so each SAN IP is reachable from a DNS name present in the same SAN: A record(s) for an alias name → IP, plus matching PTR record (verify with `ipa dnsrecord-find`)
- [ ] 2.3 Extend the relevant `certSANs` list with the alias name(s) added in 2.2 so forward reachability holds within the SAN set
- [ ] 2.4 Fresh-scenario cycle (`tox -e destroy` + `converge-monorepo`) without the monkey patch; verify all ipacert tasks succeed and inspect the issued API server cert's SAN set (original IPs present, added names present)
- [ ] 2.5 Decision gate D3b: if Test B passes → keep zone records + certSANs, document them as load-bearing (removing breaks issuance), confirm L12-28 stays removed; if it fails → restore the monkey patch and proceed to section 3

## 3. Hardened fallback — keep and harden the monkey patch (only if both tests failed)

- [ ] 3.1 Restore the `patch IPA cert.py` + `ipactl restart` tasks
- [ ] 3.2 Replace the hardcoded `/usr/lib/python3.14/site-packages/...` path with dynamic resolution (`python3 -c 'import ipaserver.plugins.cert, os; print(os.path.dirname(ipaserver.plugins.cert.__file__))'`) so the patch survives Python/distro upgrades
- [ ] 3.3 Add a comment block on the task documenting both validation layers (FreeIPA `_validate_san_ips` unconditional check vs Dogtag `disableDogtagReachabilityValidation`) and why each of the three mitigations exists

## 4. Final verification of the landed state

- [ ] 4.1 Fresh-scenario converge succeeds end-to-end (`tox -e destroy` + `converge-monorepo`)
- [ ] 4.2 Idempotence check: second converge reports no changes in `ipa-kubernetes-ca.yml` tasks (no re-patch, no spurious `ipactl restart`, no duplicate zone records)
- [ ] 4.3 Update the task comments so each surviving mitigation states which layer it covers; confirm no dead mitigation remains
