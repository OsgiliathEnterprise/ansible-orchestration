## Context

`test_master.py` already has `test_apiserver_crt_signed_by_kubernetes_ca` (checks apiserver.crt issuer). The kubelet-client and front-proxy-client certs are issued by kubernetes-ca via `ipacert` module but lack signing verification. Additionally, there's no test confirming the kubernetes-ca sub-CA itself chains to FreeIPA's root CA.

## Goals / Non-Goals

**Goals:**
- Add issuer-check tests for kubelet-client and front-proxy-client certs (same pattern as existing apiserver test)
- Verify full certificate chain: IPA root CA → kubernetes-ca → leaf certs

**Non-Goals:**
- Modifying any Ansible playbooks or production code
- Changing test infrastructure or framework

## Decisions

**Use `openssl x509 -issuer` for kubelet-client and front-proxy-client tests:** Same approach as the existing apiserver test — check that `-noout -issuer` output contains "kubernetes-ca". Consistent, lightweight, no new dependencies.

**Use `/etc/ipa/ca.crt` already present on the master (IPA client) rather than fetching over HTTP:** Port 8443 is not reachable from inside the VM network. The IPA client enrollment process installs `/etc/ipa/ca.crt`, which contains the Dogtag CA certificates (root + intermediates). Use `openssl verify -CAfile /etc/ipa/ca.crt` against `/etc/kubernetes/pki/ca.crt`.

**Alternatives considered:**
- Using `ipa-certupdate`: simpler but requires pki-tui package, and user preferred HTTP endpoint approach
- Fetching via `ipa ca-show kubernetes-ca --certificate-out=...`: would require Kerberos ticket on master for IPA server communication — more complex than HTTP fetch
- Embedding the root CA in test fixtures: brittle, breaks if cert rotates

## Risks / Trade-offs

[Risk] Dogtag endpoint URL may differ across FreeIPA versions → Mitigation: use retry logic; if test fails, adjust endpoint path during next run
[Risk] `curl -sk` requires no certificate validation — acceptable for internal test environment, not for production security testing
[Trade-off] Test writes to `/tmp/ipa-root-ca.crt`; cleanup is implicit (temp directory) rather than explicit
