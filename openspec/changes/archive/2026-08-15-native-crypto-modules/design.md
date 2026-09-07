## Context

Several task files use `ansible.builtin.shell` with `openssl` for certificate operations. The project has `community.crypto` installed (3.3.0), which provides native modules for serial extraction, CSR generation, and signature verification. DER SHA256 hash computation lacks a direct native equivalent.

## Goals / Non-Goals

**Goals:**
- Replace 4x serial number extraction in `delete-ipa-cleanup.yml` with `community.crypto.x509_certificate_info`
- Replace CSR generation in `admin-user.yml` with `community.crypto.openssl_csr`
- Note `community.crypto.openssl_signature_info` for potential future use (signature verification — not currently used in these task files)

**Non-Goals:**
- Replacing DER SHA256 hash computation — no pure Ansible module exists for this
- Replacing cert chain verification (`openssl verify`) — handled separately if needed

## Decisions

**Use `community.crypto.x509_certificate_info` for serial extraction:** The module accepts `path:` and returns `.cert.serial_number` as a structured value. This replaces fragile shell output parsing with typed data. No need for `cut -d= -f2` string manipulation.

**Use `community.crypto.openssl_csr` for CSR generation:** The module accepts `privatekey_path`, `cn`, `country_name`, etc., and outputs to `cert_path`. Replaces the current `openssl req -new` command with structured parameters, eliminating shell subject escaping issues.

**Keep DER SHA256 hash as shell:** Converting PEM→DER then computing SHA256 digest has no direct Ansible module equivalent. The minimal shell pipeline (`openssl x509 -outform DER | openssl dgst -sha256`) is acceptable here — replacing it would require a custom filter or Python code block, which is less readable than the current form.

**`community.crypto.openssl_signature_info` availability:** This module verifies file signatures against certificates (given certificate_path and signature base64). It does not perform PKI chain validation (`openssl verify -CAfile`) — those are different operations. The module is available in our `community.crypto 3.3.0` but doesn't apply to current task files' openssl usage.

## Risks / Trade-offs

[Risk] `x509_certificate_info` returns serial as an integer, not hex string → Mitigation: format with `| string | regex_replace(...)` if IPA expects hex format (check existing output)
[Trade-off] DER SHA256 hash remains as shell — acceptable since it's a minimal pipeline, not complex logic
