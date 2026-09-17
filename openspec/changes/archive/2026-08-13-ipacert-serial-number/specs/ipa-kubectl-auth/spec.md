## ADDED Requirements

### Requirement: Cleanup task extracts serial numbers from certificate files
The `delete-ipa-cleanup.yml` task SHALL extract each certificate's serial number directly from its installed file (using openssl) before revoking it through the `freeipa.ansible_freeipa.ipacert` module.

#### Scenario: Serial extracted and used for revocation
- **WHEN** the cleanup task runs with `reset_kube: true` and a certificate file exists on disk
- **THEN** the serial number is extracted from the certificate using openssl
- **THEN** the certificate is revoked via `ipacert` module with both `serial_number` set to the extracted value and `state: revoked`

#### Scenario: Missing cert does not fail teardown
- **WHEN** the cleanup task runs and a certificate file has been removed or was never issued
- **THEN** revocation for that certificate is skipped without failing the play

## MODIFIED Requirements

### Requirement: IPA certificates are revoked on teardown

When the cluster is destroyed with `reset_kube: true`, the system SHALL revoke IPA-signed certificates using their serial numbers extracted from the installed certificate files, and clean up IPA DNS records and service principals.

#### Scenario: Certs are revoked on teardown
- **WHEN** the role runs with `reset_kube: true`
- **THEN** each IPA-signed certificate's serial number is extracted from its file on disk using openssl
- **THEN** certificates are revoked via `ipacert` module with `state: revoked` and `serial_number` set to the extracted value
- **THEN** IPA DNS records for `apiserver.kubernetes.<domain>` are removed
- **THEN** IPA service principals are cleaned up
