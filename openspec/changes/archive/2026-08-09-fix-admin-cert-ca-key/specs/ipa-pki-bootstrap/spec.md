## MODIFIED Requirements

### Requirement: Admin user certificate is IPA-signed
The admin user certificate SHALL be requested from the `kubernetes-ca` via the `freeipa.ansible_freeipa.ipacert` module instead of being locally signed with the kubeadm-generated CA key.

#### Scenario: Admin cert is IPA-signed
- **WHEN** the role runs and `kubeadm.crt` does not exist
- **THEN** a private key is generated at `{{ kube_credential_folder }}/kubeadm.pem`
- **THEN** a CSR is generated with CN `kubeClusteradm` and `O=clusterAdministrators`
- **THEN** the certificate is requested via `ipacert` module with `ca=kubernetes-ca`
- **THEN** the signed certificate is placed at `{{ kube_credential_folder }}/kubeadm.crt`

#### Scenario: Admin cert already exists
- **WHEN** the role runs and `kubeadm.crt` already exists
- **THEN** no new certificate request is performed

## ADDED Requirements

### Requirement: ConfigMap is re-applied after API server stabilization
After the API server static pod restarts, the `cluster-info` ConfigMap SHALL be re-applied with the IPA CA certificate. The API server may reset the ConfigMap during startup reconciliation, so the re-application must occur after the API server is fully ready.

#### Scenario: ConfigMap has IPA CA after re-apply
- **WHEN** the role runs and the API server has restarted
- **THEN** the `cluster-info` ConfigMap is updated with the IPA CA certificate
- **THEN** the ConfigMap's CA issuer matches `kubernetes-ca`
- **THEN** the join command is reconstructed with the correct CA hash from the ConfigMap

### Requirement: Admin cert is verifiable as IPA-signed
A testinfra test SHALL verify that the admin certificate at `/home/kubecreds/kubeadm.crt` was issued by the IPA `kubernetes-ca`.

#### Scenario: Admin cert issuer check
- **WHEN** the test runs on the master host
- **THEN** the certificate's issuer matches the `kubernetes-ca` in IPA

### Requirement: kubectl can query the cluster with admin cert
A testinfra test SHALL verify that `kubectl` can successfully query the cluster.

#### Scenario: kubectl get nodes succeeds
- **WHEN** the test runs on the master host
- **THEN** `kubectl get nodes` returns at least one node

## REMOVED Requirements

### Requirement: Admin user certificate is locally signed with kubeadm CA key
**Reason**: The kubeadm-generated `ca.key` is replaced during IPA PKI swap and no longer available. Admin certs must be IPA-signed like all other control plane certs.
**Migration**: Replace `community.crypto.x509_certificate` ownca provider with `freeipa.ansible_freeipa.ipacert` module call.
