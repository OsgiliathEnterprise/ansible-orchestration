## ADDED Requirements

### Requirement: Worker kubelet authenticates API-proxied requests with x509 client certificates
A worker node's kubelet configuration SHALL enable x509 client-certificate authentication
against a merged CA bundle (`/etc/kubernetes/pki/ca-bundle.crt` containing exactly the two
FreeIPA-fetched certificates, the `kubeclusteradm` CA #2 and `kubernetes-ca` CA #1, and never
the kubeadm self-signed CA), disable anonymous authentication, and authorize via
`mode: Webhook`.

#### Scenario: Bundle installed alongside the trust anchor
- **WHEN** a worker node prepares to join
- **THEN** `/etc/kubernetes/pki/ca-bundle.crt` contains exactly the `kubeclusteradm` (CA #2) and `kubernetes-ca` (CA #1) certificates fetched from FreeIPA, and no kubeadm self-signed certificate
- **THEN** the bundle is reinstalled if `kubeadm reset` wipes `/etc/kubernetes/pki/`

#### Scenario: Worker kubelet config carries the auth blocks
- **WHEN** the minimal kubelet config is written on the worker
- **THEN** it contains `authentication.anonymous.enabled: false`, `authentication.webhook.enabled: true`, `authentication.x509.clientCAFile: /etc/kubernetes/pki/ca-bundle.crt`, and `authorization.mode: Webhook`

#### Scenario: Proxied subresources reach pods on the worker
- **WHEN** the API server proxies `kubectl exec` or `kubectl logs` for a pod scheduled on the worker
- **THEN** the kubelet accepts the API server's CA #2-issued client certificate instead of answering `401 Unauthorized`
