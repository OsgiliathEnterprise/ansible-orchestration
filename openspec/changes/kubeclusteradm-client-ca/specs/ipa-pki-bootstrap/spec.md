# Delta for ipa-pki-bootstrap

## MODIFIED Requirements

### Requirement: Kubernetes CA certificate is available on master

The master SHALL have both FreeIPA CA certificates available for the two-CA model: the cluster
trust anchor CA (`kubernetes-ca`, CA #1) at `/etc/kubernetes/pki/ca.crt.new` and the client CA
(`kubeclusteradm`, CA #2) at `/etc/kubernetes/pki/ca.crt.kubeclusteradm`.

#### Scenario: CA #1 certificate is downloaded
- **WHEN** the PKI swap runs on the master
- **THEN** the `kubernetes-ca` (CA #1) CA certificate is fetched from the IPA server (delegated) and installed at `/etc/kubernetes/pki/ca.crt.new`

#### Scenario: CA #2 certificate is downloaded
- **WHEN** the PKI swap runs on the master
- **THEN** the `kubeclusteradm` (CA #2) CA certificate is fetched from the IPA server (delegated) and installed at `/etc/kubernetes/pki/ca.crt.kubeclusteradm`

### Requirement: Kubernetes CA is installed as the cluster trust anchor

The master SHALL install the `kubernetes-ca` (CA #1) certificate as the cluster trust anchor.

#### Scenario: Trust anchor is CA #1
- **WHEN** the PKI swap installs the trust anchor
- **THEN** `/etc/kubernetes/pki/ca.crt` contains the `kubernetes-ca` (CA #1) CA certificate only

### Requirement: API server serving certificate is IPA-signed

The master SHALL request and install the API server serving certificate signed by the
`kubernetes-ca` (CA #1) CA, so the cluster trust anchor validates it.

#### Scenario: Serving certificate is CA #1-signed
- **WHEN** the API server certificate is requested
- **THEN** it is issued by the `kubernetes-ca` (CA #1) CA with the `kubeAdministrators` profile and principal `HTTP/apiserver.kubernetes.osgiliath.test`

### Requirement: Front-proxy client certificate is IPA-signed

The master SHALL request and install the front-proxy client certificate signed by the
`kubeclusteradm` (CA #2) CA.

#### Scenario: Front-proxy client certificate is CA #2-signed
- **WHEN** the front-proxy client certificate is requested
- **THEN** it is issued by the `kubeclusteradm` (CA #2) CA with the `kubeAdministrators` profile and principal `host/master.osgiliath.test`

### Requirement: Kubelet client certificate is IPA-signed

The master SHALL request and install the kubelet client certificate signed by the
`kubeclusteradm` (CA #2) CA.

#### Scenario: Kubelet client certificate is CA #2-signed
- **WHEN** the kubelet client certificate is requested
- **THEN** it is issued by the `kubeclusteradm` (CA #2) CA with the `kubeAdministrators` profile and principal `host/master.osgiliath.test`

### Requirement: API server and controller-manager trust the IPA CA

The master SHALL point the API server and controller-manager at a client CA bundle
(`/etc/kubernetes/pki/ca-bundle.crt`) that contains both the `kubeclusteradm` (CA #2) and
`kubernetes-ca` (CA #1) CA certificates.

#### Scenario: Client CA bundle is the two-CA merged bundle
- **WHEN** the client CA is installed
- **THEN** `/etc/kubernetes/pki/ca-bundle.crt` contains the `kubeclusteradm` (CA #2) CA certificate followed by the `kubernetes-ca` (CA #1) CA certificate

#### Scenario: API server uses the client CA bundle
- **WHEN** the API server static pod is patched
- **THEN** `--client-ca-file` points at `/etc/kubernetes/pki/ca-bundle.crt`

#### Scenario: Controller-manager uses the client CA bundle as root CA
- **WHEN** the controller-manager static pod is patched
- **THEN** `--root-ca-file` points at `/etc/kubernetes/pki/ca-bundle.crt`

### Requirement: Scheduler trusts the IPA CA

The master SHALL point the scheduler at the two-CA client CA bundle.

#### Scenario: Scheduler root CA is the client CA bundle
- **WHEN** the scheduler static pod is patched
- **THEN** `--root-ca-file` points at `/etc/kubernetes/pki/ca-bundle.crt`

### Requirement: Retained kubeadm CA is preserved for CSR-based signing

The master SHALL retain the kubeadm CA certificate for CSR-based cluster signing, and the
kubeadm CA SHALL NOT be part of the client CA bundle.

#### Scenario: Retained kubeadm CA is present
- **WHEN** the PKI swap retains the kubeadm CA
- **THEN** `/etc/kubernetes/pki/ca.crt.kubeadm` contains the original kubeadm CA certificate

#### Scenario: Controller-manager cluster signing uses the retained kubeadm CA
- **WHEN** the controller-manager static pod is patched
- **THEN** `--cluster-signing-cert-file` points at `/etc/kubernetes/pki/ca.crt.kubeadm`

#### Scenario: Client CA bundle does not include the kubeadm CA
- **WHEN** the client CA bundle is built
- **THEN** it contains only the `kubeclusteradm` (CA #2) and `kubernetes-ca` (CA #1) CA certificates

## ADDED Requirements

### Requirement: kubeclusteradm CA (CA #2) is provisioned on the IPA server

The IPA server SHALL host a second CA named `kubeclusteradm` (CA #2) that signs client
certificates, mirroring the `kubernetes-ca` (CA #1) bootstrap.

#### Scenario: CA #2 is created
- **WHEN** the PKI bootstrap runs
- **THEN** a FreeIPA CA `CN=kubeclusteradm` exists on the IPA server

#### Scenario: CA #2 ACL allows all user principals
- **WHEN** the CA #2 ACL is created
- **THEN** it allows `usercat=all`

#### Scenario: CA #2 is linked to the client cert profiles
- **WHEN** the CA #2 ACL is linked to profiles
- **THEN** the global profiles `kubeAdministrators` (O=system:masters) and `kubernetesNodes` (O=system:nodes) are linked to the CA #2 ACL

#### Scenario: CA #2 has no IP-SAN DNS records
- **WHEN** the CA #2 bootstrap runs
- **THEN** no DNS A or PTR records are created for the `kubeclusteradm` CA (its self-signed CA certificate carries no IP SANs)

#### Scenario: CA #2 ACL contains all cluster hosts
- **WHEN** the CA #2 ACL host grants run (master-only, delegated to the IPA server)
- **THEN** the `kubeclusteradm` CA ACL contains every cluster host (the IPA server, the master, and all nodes), so host-principal renewals (front-proxy as `host/<master>`, node-client as `host/<node>`) are allowed despite `usercat=all` not covering host principals

### Requirement: Controller-manager and scheduler client certs are re-issued by the kubeclusteradm CA

The kubeadm-generated controller-manager and scheduler client certificates are signed by the
kubeadm CA (CA #0), which the two-CA client CA bundle does not include; the master SHALL
re-issue both client certificates from the `kubeclusteradm` (CA #2) CA so they are trusted by
the new client CA bundle. The exact `system:masters` subjects SHALL be reproduced with static
certificate profiles (`kubeControllerManager`, `kubeScheduler`) linked to the CA #2 ACL, since
the CSR's CN is constrained by the host-principal check and the profile rewrites the issued
subject.

#### Scenario: Static-subject profiles are linked to the CA #2 ACL
- **WHEN** the CA #2 ACL is linked to profiles
- **THEN** the global profiles `kubeControllerManager` (subject `CN=system:kube-controller-manager, O=system:masters`) and `kubeScheduler` (subject `CN=system:kube-scheduler, O=system:masters`) are linked to the CA #2 ACL

#### Scenario: Controller-manager client cert is CA #2-signed with the exact subject
- **WHEN** the controller-manager client certificate is re-issued
- **THEN** it is issued by the `kubeclusteradm` (CA #2) CA with the `kubeControllerManager` profile and subject `CN=system:kube-controller-manager, O=system:masters`

#### Scenario: Scheduler client cert is CA #2-signed with the exact subject
- **WHEN** the scheduler client certificate is re-issued
- **THEN** it is issued by the `kubeclusteradm` (CA #2) CA with the `kubeScheduler` profile and subject `CN=system:kube-scheduler, O=system:masters`

#### Scenario: Client credentials are embedded for the scheduler
- **WHEN** the re-issued client credentials are installed
- **THEN** `controller-manager.conf` and `scheduler.conf` carry the CA #2 client certificate and key (embedded as base64 `client-certificate-data` / `client-key-data` for the scheduler static pod, which mounts only its conf), and both static pods are restarted

### Requirement: PKI swap verification runs after the admin credential re-issue

The `ipa-pki-swap` verification tasks (controller-manager lease gate, node Ready gate) and the
`kubeclusteradm` admin `kubectl get nodes` verification SHALL run after `admin-user.yml` has
re-issued the admin client cert from CA #2 and re-embedded it in `admin.conf`, because the new
client CA bundle no longer trusts the previous (CA #0-issued) admin cert.

#### Scenario: Swap gates authenticate with a CA #2 admin cert
- **WHEN** the PKI swap verifies cluster health
- **THEN** `main.yml` has run `admin-user.yml` (admin cert re-issue + `admin.conf` re-embed) before `ipa-pki-swap.yml`, so the gate tasks authenticate with a CA #2-issued admin cert

#### Scenario: Admin `kubectl` verification runs after the re-embed
- **WHEN** the `kubeclusteradm` admin credential is verified with `kubectl get nodes`
- **THEN** the verification runs at the end of `admin-user.yml`, after the CA #2 cert has been re-embedded in `admin.conf`
