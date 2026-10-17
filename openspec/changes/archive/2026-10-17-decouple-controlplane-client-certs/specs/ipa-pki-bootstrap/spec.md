# Delta for ipa-pki-bootstrap

## MODIFIED Requirements

### Requirement: Controller-manager and scheduler client certs are re-issued by the kubeclusteradm CA
The kubeadm-generated controller-manager and scheduler client certificates are signed by the
kubeadm CA (CA #0), which the two-CA client CA bundle does not include; the master SHALL
re-issue both client certificates from the `kubeclusteradm` (CA #2) CA so they are trusted by
the new client CA bundle. The exact `system:masters` subjects SHALL be reproduced with static
certificate profiles (`kubeControllerManager`, `kubeScheduler`) linked to the CA #2 ACL, since
the CSR's CN is constrained by the host-principal check and the profile rewrites the issued
subject. Each component's re-issue SHALL be independently gated on the issuer of the client
certificate embedded in its own conf, so neither component's gate result SHALL skip the other
component's re-issue.

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

#### Scenario: Re-issue is independently gated per component
- **WHEN** the re-issue gate for one component runs
- **THEN** it is decided from the issuer of the client certificate embedded in that component's own conf (`controller-manager.conf` / `scheduler.conf`), and neither component's gate result skips the other component's re-issue

#### Scenario: Partial failure is repaired on re-converge
- **WHEN** a re-converge runs and `controller-manager.conf` already carries a CA #2-signed client certificate but `scheduler.conf` still carries a CA #0-signed client certificate
- **THEN** the controller-manager re-issue is skipped and the scheduler re-issue runs

#### Scenario: Completed re-issue is skipped without churn
- **WHEN** a re-converge runs and a component's conf already carries a CA #2-signed client certificate
- **THEN** that component's key/CSR/cert are not regenerated, its conf is not re-embedded, and its static pod is not restarted
