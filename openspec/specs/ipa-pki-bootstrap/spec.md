# IPA PKI Bootstrap

## Purpose

After `kubeadm init`, swap the kubeadm-generated PKI with certificates signed by the FreeIPA `kubernetes-ca` sub-CA. This includes the API server certificate, front-proxy client certificate, kubelet client certificate, and service account key, ensuring all Kubernetes control plane components trust the IPA CA.

## Requirements

### Requirement: IPA PKI bootstrap runs unconditionally on masters
The IPA PKI bootstrap tasks SHALL execute on every master host without requiring a boolean toggle.

#### Scenario: IPA PKI runs on masters
- **WHEN** the role runs and the host is in `kube_masters_group`
- **THEN** IPA PKI infrastructure setup executes
- **THEN** IPA PKI certificate swap executes

### Requirement: Kubernetes CA certificate is available on master
The system SHALL download the `kubernetes-ca` certificate and place it at `/etc/kubernetes/pki/ca.crt` on the Kubernetes master.

#### Scenario: CA certificate is downloaded
- **WHEN** the role runs
- **THEN** the `kubernetes-ca` certificate is written to `/etc/kubernetes/pki/ca.crt`
- **THEN** the file is owned by root with mode 0644

### Requirement: API server certificate is IPA-signed
The system SHALL generate a private key and CSR for the API server, request a certificate from the `kubernetes-ca` via the `freeipa.ansible_freeipa.ipacert` module, and place the signed certificate at `/etc/kubernetes/pki/apiserver.crt`.

#### Scenario: API server cert is requested and placed
- **WHEN** the role runs and `apiserver.crt` does not exist
- **THEN** a private key is generated at `/etc/kubernetes/pki/apiserver.key`
- **THEN** a CSR is generated with CN matching `apiserver.kubernetes.<company_domain>` and SANs including the master hostname, master IP, and any `kube_alt_names`
- **THEN** the certificate is requested via `ipacert` module with `principal=HTTP/apiserver.kubernetes.<company_domain>`, `ca=kubernetes-ca`
- **THEN** the signed certificate is placed at `/etc/kubernetes/pki/apiserver.crt`

#### Scenario: API server cert already exists
- **WHEN** the role runs and `apiserver.crt` already exists
- **THEN** no new certificate request is performed and the task reports no change

### Requirement: Front-proxy client certificate is IPA-signed
The system SHALL generate a private key and CSR for the front-proxy client, request a certificate from the `kubernetes-ca` via the `ipacert` module, and place the signed certificate at `/etc/kubernetes/pki/front-proxy-client.crt`.

#### Scenario: Front-proxy cert is requested and placed
- **WHEN** the role runs and `front-proxy-client.crt` does not exist
- **THEN** a private key is generated at `/etc/kubernetes/pki/front-proxy-client.key`
- **THEN** a CSR is generated with CN matching the master hostname
- **THEN** the certificate is requested via `ipacert` module with `ca=kubernetes-ca`
- **THEN** the signed certificate is placed at `/etc/kubernetes/pki/front-proxy-client.crt`

### Requirement: Kubelet client certificate is IPA-signed
The system SHALL generate a private key and CSR for the kubelet client, request a certificate from the `kubernetes-ca` via the `ipacert` module with the `kubeAdministrators` profile, and place the signed certificate at `/etc/kubernetes/pki/apiserver-kubelet-client.crt`.

#### Scenario: Kubelet client cert is requested and placed
- **WHEN** the role runs and `apiserver-kubelet-client.crt` does not exist
- **THEN** a private key is generated at `/etc/kubernetes/pki/apiserver-kubelet-client.key`
- **THEN** a CSR is generated with `O=system:masters` and CN matching the master hostname
- **THEN** the certificate is requested via `ipacert` module with `ca=kubernetes-ca`, `profile_id=kubeAdministrators`
- **THEN** the signed certificate is placed at `/etc/kubernetes/pki/apiserver-kubelet-client.crt`

### Requirement: Admin user principal is created via native ipauser module
The `kubeclusteradm` IPA user principal SHALL be created via the `freeipa.ansible_freeipa.ipauser` Ansible module and SHALL NOT use a shell-based `ipa user-add` command. The principal SHALL be created with first name `kube`, last name `ClusterAdmin`, the configured admin email address, and the realm password.

#### Scenario: Principal is created when missing
- **WHEN** the role runs on the IPA server and the `kubeclusteradm` principal does not exist
- **THEN** the principal is created via the `freeipa.ansible_freeipa.ipauser` module with first name `kube`, last name `ClusterAdmin`, the configured admin email address, and the realm password

#### Scenario: Principal creation is idempotent
- **WHEN** the role runs on the IPA server and the `kubeclusteradm` principal already exists
- **THEN** no error is raised and the task reports that the principal is already present

#### Scenario: No shell user-add for admin principal
- **WHEN** the role runs
- **THEN** no shell-based `ipa user-add` command is executed to create the `kubeclusteradm` principal

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

### Requirement: SA key is generated locally
The system SHALL generate a private key for service account token signing at `/etc/kubernetes/pki/sa.key`.

#### Scenario: SA key is generated
- **WHEN** the role runs and `sa.key` does not exist
- **THEN** an ECDSA private key is generated at `/etc/kubernetes/pki/sa.key`

### Requirement: Certificate requests use ipacert module
All certificate requests SHALL use the `freeipa.ansible_freeipa.ipacert` Ansible module and SHALL NOT use shell-based `ipa cert-request` commands.

#### Scenario: No shell cert requests
- **WHEN** the role runs
- **THEN** all certificate requests are performed via `freeipa.ansible_freeipa.ipacert` module calls
- **THEN** no `ipa cert-request` shell commands are executed

### Requirement: IPA PKI swap runs after kubeadm init
The IPA PKI certificate generation and swap tasks SHALL complete after the `kubeadm init` command has succeeded.

#### Scenario: Correct execution order
- **WHEN** the role runs
- **THEN** `kubeadm init` completes successfully with its own PKI
- **THEN** IPA PKI tasks generate certificates and swap into `/etc/kubernetes/pki/`
- **THEN** component configs are patched to trust the IPA CA
- **THEN** the API server static pod is restarted to pick up new certificates

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

### Requirement: Stale kubeadm state cleanup runs during teardown
Stale kubeadm configuration files SHALL be cleaned during the reset phase, not during the install phase.

#### Scenario: Stale state cleaned on reset
- **WHEN** `reset_kube` is true
- **THEN** stale kubeadm config files (`admin.conf`, `controller-manager.conf`, `scheduler.conf`, `boottstrap-token.conf`, `kubelet.conf`, `pki/`) are removed before `kubeadm reset -f`

#### Scenario: No stale cleanup on fresh install
- **WHEN** `reset_kube` is false or undefined
- **THEN** no kubeadm state cleanup is performed in `kube-install.yml`

### Requirement: Controller-manager and scheduler configs trust IPA CA
After the PKI swap, the `controller-manager.conf` and `scheduler.conf` files SHALL reference the IPA CA certificate.

#### Scenario: Component configs are patched
- **WHEN** the role runs
- **THEN** `controller-manager.conf` references `/etc/kubernetes/pki/ca.crt` as certificate authority
- **THEN** `scheduler.conf` references `/etc/kubernetes/pki/ca.crt` as certificate authority
