# Kube Cert Renewal (delta)

## MODIFIED Requirements

### Requirement: Renewal is idempotent and churn-free
A timer tick SHALL act only on certificates whose remaining validity has dropped below the renewal threshold (a role default, 30 days by default). When no certificate is due, a tick MUST be a no-op — it MUST NOT re-issue unchanged certificates or restart services unnecessarily. The converge-time certificate gates established by the `steady-state-idempotence` capability SHALL evaluate eligibility against the same threshold from the same single source, so the timer and a converge never disagree about whether a certificate is due.

#### Scenario: No-op when nothing is eligible
- **WHEN** the timer fires while all cluster certificates are still well within their validity window
- **THEN** no certificate is rewritten and no service is restarted by that tick

#### Scenario: Converge gate and timer agree on eligibility
- **WHEN** a certificate's remaining validity is above the configured threshold
- **THEN** neither the timer tick nor a converge re-issues it
- **AND** when the remaining validity drops below the threshold, both the timer and a converge treat it as eligible

### Requirement: Renewal setup converges idempotently with accurate change reporting
The renewal-setup tasks that grant kubernetes-ca ACL access to each kube host and generate the `kubeclusteradm` keytab SHALL be re-runnable without failing. When a precondition is already satisfied (the host is already listed in `kubernetes-ca-acl`, or the keytab already exists), the task SHALL report no change; when it performs work, it SHALL report changed. Each loop item's outcome SHALL be evaluated against that item's own result, so per-host outcomes are reported independently within a single run. Conditional add-type tasks driven by a helper script (CA ACL grants, service-category sets) SHALL derive the task's changed status from the helper's stdout marker tokens (`CA-ACL-ADDED`, `SERVICECAT-SET`) rather than reporting changed unconditionally.

#### Scenario: Re-converge on an already-converged cluster is green
- **WHEN** renewal setup runs again after every kube host already has kubernetes-ca ACL access and the `kubeclusteradm` keytab exists
- **THEN** the ACL-grant task reports no change for every host, the keytab task reports no change, and no task fails with an undefined-variable error

#### Scenario: Mixed state within one run evaluates per host
- **WHEN** renewal setup runs in a state where some hosts already have kubernetes-ca ACL access and others do not
- **THEN** each already-listed host's item reports no change while each newly added host's item reports changed, all within the same task run

#### Scenario: Steady-state CA ACL re-assert reports ok
- **WHEN** the steady-state CA ACL re-assert loop runs and every required CA already lists every required host
- **THEN** the loop task reports `ok`, not `changed`
