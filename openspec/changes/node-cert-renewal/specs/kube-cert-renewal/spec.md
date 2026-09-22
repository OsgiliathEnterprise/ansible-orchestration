## Purpose

Defines how all IPA-issued Kubernetes cluster certificates are continuously renewed so the cluster stays healthy past individual certificate validity windows, without manual re-convergence.

## ADDED Requirements

### Requirement: Continuous renewal via a per-host timer
Every host that holds a cluster certificate (the master and every worker) SHALL run a scheduled timer that triggers certificate renewal on a recurring basis. Renewal SHALL be continuous and self-healing — it MUST NOT depend on an Ansible converge run occurring.

#### Scenario: Timer installed and active on all hosts
- **WHEN** the role converges a cluster with a master and N workers
- **THEN** each of those hosts has an active, persistent timer that triggers certificate renewal on schedule (`systemctl list-timers` shows it enabled)

#### Scenario: Renewal occurs without a converge run
- **WHEN** no Ansible converge is executed but a certificate becomes eligible for renewal
- **THEN** the per-host timer still renews it, so liveness does not depend on operator action

### Requirement: Native FreeIPA renewal mechanism
Renewal SHALL use native FreeIPA renewal (`ipa-cert-renew`) rather than re-issuing via a fresh CSR. The relevant profiles and CA SHALL be configured to permit renewal so the in-place renew succeeds while preserving each certificate's identity (subject/principal).

#### Scenario: Certificate renewed in place
- **WHEN** an eligible cluster certificate is renewed by the timer
- **THEN** it is extended with its subject/principal unchanged (no new serial/identity churn) and a later `notAfter`

#### Scenario: Profile permits renewal
- **WHEN** the node, admin, and control-plane profiles are inspected after convergence
- **THEN** each is configured to allow renewal so `ipa-cert-renew` can act on its certificates

### Requirement: All expiring cluster certificates are covered
Renewal SHALL cover every IPA-issued cluster certificate that carries a finite validity: worker node certs, the master admin cert, and control-plane component certs. No cluster certificate SHALL be left to expire unattended.

#### Scenario: Worker node certificate renewed
- **WHEN** a worker's `system:node:<host>` certificate becomes eligible for renewal
- **THEN** it is renewed so the kubelet continues to authenticate and the node stays Ready

#### Scenario: Master admin certificate renewed
- **WHEN** the master admin (`kubeclusteradm`) certificate becomes eligible for renewal
- **THEN** it is renewed so operator access via `admin.conf` remains valid

#### Scenario: Control-plane component certificates renewed
- **WHEN** a control-plane component certificate (API server, front-proxy) becomes eligible for renewal
- **THEN** it is renewed so the affected component continues to present a valid client certificate

### Requirement: Renewed certificate is deployed and the service reloaded
After a successful renewal, the new certificate SHALL be deployed to its expected path and the affected service reloaded or restarted so the running component actually uses the renewed certificate.

#### Scenario: Worker kubelet picks up the renewed certificate
- **WHEN** a worker's node certificate is renewed
- **THEN** it is placed at the kubelet's client-cert path and the kubelet reloads, with the node remaining Ready

#### Scenario: Master admin.conf reflects the renewed certificate
- **WHEN** the master admin certificate is renewed
- **THEN** `admin.conf` references the renewed certificate and `kubectl` via that config still authenticates successfully

### Requirement: Renewal is idempotent and churn-free
A timer tick SHALL act only on certificates actually eligible for renewal. When no certificate is due, a tick MUST be a no-op — it MUST NOT redeploy unchanged certificates or restart services unnecessarily.

#### Scenario: No-op when nothing is eligible
- **WHEN** the timer fires while all cluster certificates are still well within their validity window
- **THEN** no certificate is rewritten and no service is restarted by that tick
