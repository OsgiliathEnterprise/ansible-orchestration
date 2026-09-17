## Why

The `delete-ipa-cleanup.yml` task revokes IPA certificates using only `certificate_name`, but the `freeipa.ansible_freeipa.ipacert` module's `serial_number` parameter provides a more reliable way to identify which certificate to revoke. Rather than capturing serial numbers during issuance, we can extract them directly from the installed certificate files at teardown time using openssl — eliminating cross-play persistence entirely.

## What Changes

- Update `delete-ipa-cleanup.yml` to extract each certificate's serial number from its file on disk using `openssl x509 -serial`
- Use the extracted `serial_number` when calling the `ipacert` module with `state: revoked`
- Add stat-based guards so missing cert files don't fail teardown

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ipa-kubectl-auth`: The cert revocation requirement changes from using `certificate_name` to extracting and using `serial_number` from the installed certificate files.

## Impact

- `tasks/delete-ipa-cleanup.yml` — add serial extraction and use in revocation calls