## MODIFIED Requirements

### Requirement: Controller-manager and scheduler configs trust IPA CA
After the PKI swap, the controller-manager and scheduler static pod manifests SHALL be patched so client authentication trusts both CAs (the merged bundle) while cluster certificate signing continues with the retained kubeadm CA.

#### Scenario: Component configs are patched
- **WHEN** the role runs on a master after the CA swap
- **THEN** the controller-manager manifest's `--client-ca-file` references `/etc/kubernetes/pki/ca-bundle.crt` (kubeadm + IPA CAs)
- **THEN** the controller-manager manifest's `--cluster-signing-cert-file` references `/etc/kubernetes/pki/ca.crt.kubeadm` (retained kubeadm CA for cluster cert signing)
- **THEN** the controller-manager manifest's `--root-ca-file` references `/etc/kubernetes/pki/ca-bundle.crt`
- **THEN** if present, the scheduler manifest's `--root-ca-file` references `/etc/kubernetes/pki/ca-bundle.crt`
