## Why

Several task files use `ansible.builtin.shell` with `openssl` commands for certificate operations that have native Ansible equivalents in `community.crypto`. This loses idempotency, structured output, and proper change detection.

## What Changes

- Replace 4x serial number extraction (`openssl x509 -serial`) in `delete-ipa-cleanup.yml` with `community.crypto.x509_certificate_info`
- Replace CSR generation (`openssl req -new`) in `admin-user.yml` with `community.crypto.openssl_csr`
- Note: DER SHA256 hash computation has no direct native equivalent — remains as shell

## Capabilities

### New Capabilities

(None — pure refactor)

### Modified Capabilities

(None — no spec-level behavior changes)

## Impact

- `tasks/delete-ipa-cleanup.yml` — 4 serial extraction tasks rewritten
- `tasks/admin-user.yml` — 1 CSR generation task rewritten
- No new dependencies required (`community.crypto` already installed)
