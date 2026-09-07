## MODIFIED Requirements

### Requirement: Stale kubeadm state cleanup runs during teardown
Stale kubeadm configuration files SHALL be cleaned during the reset phase, not during the install phase.

#### Scenario: Stale state cleaned on reset
- **WHEN** `reset_kube` is true
- **THEN** stale kubeadm config files (`admin.conf`, `controller-manager.conf`, `scheduler.conf`, `boottstrap-token.conf`, `kubelet.conf`, `pki/`) are removed before `kubeadm reset -f`

#### Scenario: No stale cleanup on fresh install
- **WHEN** `reset_kube` is false or undefined
- **THEN** no kubeadm state cleanup is performed in `kube-install.yml`
