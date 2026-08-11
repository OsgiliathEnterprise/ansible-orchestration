# IPA Kubectl Auth

## Purpose

Manage Kubernetes admin user authentication using IPA-signed certificates. The admin user certificate is generated via the FreeIPA PKI `kubernetes-ca` sub-CA, and the kubeconfig is configured to trust the IPA CA for client authentication.

## Requirements

### Requirement: Admin user certificate is IPA-signed
The system SHALL generate a private key and CSR for the cluster administrator, request a certificate from the `kubernetes-ca` via the `ipacert` module using the `kubeAdministrators` profile, and place the signed certificate in the credential folder.

#### Scenario: Admin cert is IPA-signed
- **WHEN** the role runs and the admin certificate does not exist
- **THEN** a private key is generated at `/home/kubecreds/kubeadm.pem`
- **THEN** a CSR is generated with `O=system:masters` and CN=`kubeClusteradm`
- **THEN** the certificate is requested via `ipacert` module with `ca=kubernetes-ca`, `profile_id=kubeAdministrators`
- **THEN** the signed certificate is placed at `/home/kubecreds/kubeadm.crt`

#### Scenario: Admin cert already exists
- **WHEN** the role runs and the admin certificate already exists
- **THEN** no new certificate request is performed and the task reports no change

### Requirement: Kubeconfig trusts kubernetes-ca
The kubeconfig used for `kubectl` authentication SHALL reference the `kubernetes-ca` certificate as the certificate authority. Trust is achieved automatically because `admin.conf` references `/etc/kubernetes/pki/ca.crt` by path, which is replaced with the `kubernetes-ca` cert during the `ipa-pki-bootstrap` swap.

#### Scenario: Kubeconfig CA is set to kubernetes-ca
- **WHEN** the role runs
- **THEN** `/etc/kubernetes/pki/ca.crt` contains the `kubernetes-ca` certificate (from `ipa-pki-bootstrap`)
- **THEN** the kubeconfig at `/etc/kubernetes/admin.conf` references `/etc/kubernetes/pki/ca.crt` as `certificate-authority`
- **THEN** `kubectl` commands using this kubeconfig trust certificates signed by `kubernetes-ca`

### Requirement: Kubeconfig credentials reference IPA-signed cert
The kubeconfig SHALL reference the IPA-signed admin certificate and key for client authentication.

#### Scenario: Kubeconfig credentials are set
- **WHEN** the role runs
- **THEN** the kubeconfig contains `client-certificate` pointing to `/home/kubecreds/kubeadm.crt`
- **THEN** the kubeconfig contains `client-key` pointing to `/home/kubecreds/kubeadm.pem`

### Requirement: IPA certificates are revoked on teardown
When the cluster is destroyed with `reset_kube: true`, the system SHALL revoke IPA-signed certificates and clean up IPA DNS records and service principals.

#### Scenario: Certs are revoked on teardown
- **WHEN** the role runs with `reset_kube: true`
- **THEN** IPA-signed certificates are revoked via `ipacert` module with `state: revoked`
- **THEN** IPA DNS records for `apiserver.kubernetes.<domain>` are removed
- **THEN** IPA service principals are cleaned up
