# Spec Delta

## ADDED Requirements

### Requirement: Renewal setup converges idempotently with accurate change reporting
The renewal-setup tasks that grant kubernetes-ca ACL access to each kube host and generate the `kubeclusteradm` keytab SHALL be re-runnable without failing. When a precondition is already satisfied (the host is already listed in `kubernetes-ca-acl`, or the keytab already exists), the task SHALL report no change; when it performs work, it SHALL report changed. Each loop item's outcome SHALL be evaluated against that item's own result, so per-host outcomes are reported independently within a single run.

#### Scenario: Re-converge on an already-converged cluster is green
- **WHEN** renewal setup runs again after every kube host already has kubernetes-ca ACL access and the `kubeclusteradm` keytab exists
- **THEN** the ACL-grant task reports no change for every host, the keytab task reports no change, and no task fails with an undefined-variable error

#### Scenario: Mixed state within one run evaluates per host
- **WHEN** renewal setup runs in a state where some hosts already have kubernetes-ca ACL access and others do not
- **THEN** each already-listed host's item reports no change while each newly added host's item reports changed, all within the same task run
