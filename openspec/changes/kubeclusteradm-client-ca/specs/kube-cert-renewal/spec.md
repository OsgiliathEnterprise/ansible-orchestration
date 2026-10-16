# Delta for kube-cert-renewal

## MODIFIED Requirements

### Requirement: All expiring cluster certificates are covered
Renewal SHALL cover every IPA-issued cluster certificate that carries a finite validity: worker node certs, the master admin cert, and control-plane component certs (API server serving cert, front-proxy client cert, controller-manager client cert, scheduler client cert). No cluster certificate SHALL be left to expire unattended. The controller-manager and scheduler client certs (re-issued from the `kubeclusteradm` CA with static-subject profiles) SHALL be renewed the same way they are re-issued at convergence.

#### Scenario: Worker node certificate renewed
- **WHEN** a worker's `system:node:<host>` certificate becomes eligible for renewal
- **THEN** it is renewed so the kubelet continues to authenticate and the node stays Ready

#### Scenario: Master admin certificate renewed
- **WHEN** the master admin (`kubeclusteradm`) certificate becomes eligible for renewal
- **THEN** it is renewed so operator access via `admin.conf` remains valid

#### Scenario: Control-plane component certificates renewed
- **WHEN** a control-plane component certificate (API server, front-proxy, controller-manager, scheduler) becomes eligible for renewal
- **THEN** it is renewed so the affected component continues to present a valid client certificate

#### Scenario: Controller-manager and scheduler confs re-embed the renewed cert
- **WHEN** the controller-manager or scheduler client certificate is renewed
- **THEN** the renewed certificate is re-embedded into the base64-embedded `controller-manager.conf` / `scheduler.conf` and the affected static pod is restarted
