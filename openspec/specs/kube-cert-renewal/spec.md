# Kube Cert Renewal

## Purpose

Defines how all IPA-issued Kubernetes cluster certificates are continuously renewed so the cluster stays healthy past individual certificate validity windows, without manual re-convergence.

## Requirements

### Requirement: Continuous renewal via a per-host timer
Every host that holds a cluster certificate (the master and every worker) SHALL run a scheduled timer that triggers certificate renewal on a recurring basis. Renewal SHALL be continuous and self-healing — it MUST NOT depend on an Ansible converge run occurring.

#### Scenario: Timer installed and active on all hosts
- **WHEN** the role converges a cluster with a master and N workers
- **THEN** each of those hosts has an active, persistent timer that triggers certificate renewal on schedule (`systemctl list-timers` shows it enabled)

#### Scenario: Renewal occurs without a converge run
- **WHEN** no Ansible converge is executed but a certificate becomes eligible for renewal
- **THEN** the per-host timer still renews it, so liveness does not depend on operator action

### Requirement: Identity-preserving keytab-driven renewal
Renewal SHALL re-issue each eligible certificate via `ipa cert-request --ca=kubernetes-ca`, authenticated with a Kerberos keytab (host keytab for node/control-plane certs, the `kubeclusteradm` user keytab for the admin cert) — no administrator password SHALL be required at runtime. The renewed certificate SHALL preserve its identity: same subject/principal and same private key as before.

#### Scenario: Certificate renewed with identity preserved
- **WHEN** an eligible cluster certificate is renewed by the timer
- **THEN** the new certificate has the same subject/principal, uses the same private key, and carries a later `notAfter`

#### Scenario: Renewal requires no admin credentials at runtime
- **WHEN** the timer renews a certificate
- **THEN** it authenticates using only a local keytab (no interactive or stored administrator password)

#### Scenario: CA ACL permits each principal type
- **WHEN** the CA ACL for `kubernetes-ca` is inspected after convergence
- **THEN** it grants the worker/master hosts and the user category so every cluster certificate's principal can be re-issued

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
A timer tick SHALL act only on certificates whose remaining validity has dropped below the renewal threshold (default 30 days). When no certificate is due, a tick MUST be a no-op — it MUST NOT re-issue unchanged certificates or restart services unnecessarily.

#### Scenario: No-op when nothing is eligible
- **WHEN** the timer fires while all cluster certificates are still well within their validity window
- **THEN** no certificate is rewritten and no service is restarted by that tick

### Requirement: Renewal setup converges idempotently with accurate change reporting
The renewal-setup tasks that grant kubernetes-ca ACL access to each kube host and generate the `kubeclusteradm` keytab SHALL be re-runnable without failing. When a precondition is already satisfied (the host is already listed in `kubernetes-ca-acl`, or the keytab already exists), the task SHALL report no change; when it performs work, it SHALL report changed. Each loop item's outcome SHALL be evaluated against that item's own result, so per-host outcomes are reported independently within a single run.

#### Scenario: Re-converge on an already-converged cluster is green
- **WHEN** renewal setup runs again after every kube host already has kubernetes-ca ACL access and the `kubeclusteradm` keytab exists
- **THEN** the ACL-grant task reports no change for every host, the keytab task reports no change, and no task fails with an undefined-variable error

#### Scenario: Mixed state within one run evaluates per host
- **WHEN** renewal setup runs in a state where some hosts already have kubernetes-ca ACL access and others do not
- **THEN** each already-listed host's item reports no change while each newly added host's item reports changed, all within the same task run

### Requirement: SAN-validation DNS preconditions are owned by infrastructure roles
Certificate requests carrying IP SANs SHALL succeed without renewal tasks modifying resolver configuration. The scoped dual-nameserver resolved config installed by `tcharl.freeipa_server` (idm) and `tcharl.ansible_securehost` (clients) during prepare SHALL satisfy IPA's zone discovery for IP SANs, and renewal tasks MUST NOT write to `/etc/systemd/resolved.conf.d`.

#### Scenario: IP-SAN request succeeds without renewal touching resolver config
- **WHEN** a certificate request with an IP SAN is issued on the IPA server host after a converged prepare+converge cycle
- **THEN** zone discovery resolves through local bind and no IP SAN is reported unreachable
- **AND** no task in the renewal flow wrote or restarted `/etc/systemd/resolved.conf.d`

#### Scenario: Renewal setup leaves the drop-in untouched
- **WHEN** renewal setup runs on a converged cluster
- **THEN** `/etc/systemd/resolved.conf.d/head.conf` content is unchanged from what the infrastructure roles deployed (scoped dual-nameserver config)
