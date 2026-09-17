## MODIFIED Requirements

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

### Requirement: Controller-manager and scheduler configs trust IPA CA
After the PKI swap, the `controller-manager.conf` and `scheduler.conf` files SHALL reference the IPA CA certificate.

#### Scenario: Component configs are patched
- **WHEN** the role runs
- **THEN** `controller-manager.conf` references `/etc/kubernetes/pki/ca.crt` as certificate authority
- **THEN** `scheduler.conf` references `/etc/kubernetes/pki/ca.crt` as certificate authority

## REMOVED Requirements

### Requirement: IPA PKI bootstrap is gated by use_ipa_pki
**Reason**: IPA PKI is now always enabled; the `use_ipa_pki` toggle has been removed.
**Migration**: All IPA PKI tasks run unconditionally on masters. The `use_ipa_pki` variable has been removed from defaults and converge files.
