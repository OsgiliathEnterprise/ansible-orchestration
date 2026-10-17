# Spec Delta

## ADDED Requirements

### Requirement: SAN-validation DNS preconditions are owned by infrastructure roles
Certificate requests carrying IP SANs SHALL succeed without renewal tasks modifying resolver configuration. The scoped dual-nameserver resolved config installed by `tcharl.freeipa_server` (idm) and `tcharl.ansible_securehost` (clients) during prepare SHALL satisfy IPA's zone discovery for IP SANs, and renewal tasks MUST NOT write to `/etc/systemd/resolved.conf.d`.

#### Scenario: IP-SAN request succeeds without renewal touching resolver config
- **WHEN** a certificate request with an IP SAN is issued on the IPA server host after a converged prepare+converge cycle
- **THEN** zone discovery resolves through local bind and no IP SAN is reported unreachable
- **AND** no task in the renewal flow wrote or restarted `/etc/systemd/resolved.conf.d`

#### Scenario: Renewal setup leaves the drop-in untouched
- **WHEN** renewal setup runs on a converged cluster
- **THEN** `/etc/systemd/resolved.conf.d/head.conf` content is unchanged from what the infrastructure roles deployed (scoped dual-nameserver config)
