## Context

Currently `delete-ipa-cleanup.yml` revokes only the admin cert using `certificate_name: "kubeclusteradm"`. The `freeipa.ansible_freeipa.ipacert` module supports a `serial_number` parameter for more reliable certificate identification during revocation. Serial numbers can be extracted from the installed certificate files at teardown time using openssl — no cross-play persistence needed.

Five tasks issue IPA-signed certificates to known paths:
- `/home/kubecreds/kubeadm.crt` (admin cert)
- `{{ kubernetes_certificates_path }}/apiserver-kubelet-client.crt`
- `{{ kubernetes_certificates_path }}/apiserver.crt`
- `{{ kubernetes_certificates_path }}/front-proxy-client.crt`

## Goals / Non-Goals

**Goals:**
- Extract serial numbers from installed certificate files during teardown using openssl
- Update `delete-ipa-cleanup.yml` to revoke using `serial_number` per spec

**Non-Goals:**
- Revoking certificates that were not issued by this role
- Modifying the FreeIPA server configuration or CA setup
- Changing certificate request logic (CSRs, profiles, etc.)
- Persisting serial numbers across plays — we read them from cert files at cleanup time instead

## Decisions

### Extract serials from cert files at teardown time
Rather than capturing and persisting serial numbers during issuance, the cleanup task will extract each serial number directly from the installed certificate file using `openssl x509 -in <cert-path> -serial`. This is simpler: no cross-play persistence, no JSON file to manage, and the serial always matches whatever cert is actually on disk.

### Cleanup reads serials with stat-based guards
The cleanup task will first check if each cert file exists (via `stat`). If it does, extract the serial number and revoke. If it doesn't exist, skip that certificate's revocation silently. All revocations remain wrapped in `failed_when: false`.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Cert file is absent at teardown (removed manually or by another process) | Stat guard skips revocation; no failure |
| Cert file exists but isn't IPA-signed | Revocation will fail silently (`failed_when: false`); harmless |