## Purpose

Define how the Kubernetes CA certificate flow obtains IP reachability on the IPA server: every service-IP used in the Dogtag/FreeIPA reachability checks is derived from the `kube_service_cidr` variable, never hard-coded.

## ADDED Requirements

### Requirement: Service cluster IP is derived from the service CIDR
Every IP used for Kubernetes CA reachability checks and records SHALL be derived from `kube_service_cidr` (default `10.96.0.0/12`) as its first usable IP. No such IP SHALL be hard-coded.

#### Scenario: Default CIDR
- **WHEN** `kube_service_cidr` is unset or `10.96.0.0/12`
- **THEN** the derived service cluster IP is `10.96.0.1`

#### Scenario: Overridden CIDR
- **WHEN** `kube_service_cidr` is `172.16.0.0/12`
- **THEN** the derived service cluster IP is `172.16.0.1`
- **THEN** all reachability consumers (hosts entry, DNS zone, A record, PTR record, cert SANs) agree on `172.16.0.1`

### Requirement: IPA server hosts entry for the service cluster IP
The IPA server's `/etc/hosts` SHALL contain an entry mapping the derived service cluster IP to `orchestration_host_hostname`, so the Dogtag reachability check can resolve the service IP.

#### Scenario: Hosts entry present
- **WHEN** the `ipa-kubernetes-ca` flow runs
- **THEN** `/etc/hosts` on the first IPA server contains a line mapping the derived service cluster IP to `{{ orchestration_host_hostname }}`

#### Scenario: Hosts entry follows the CIDR
- **WHEN** `kube_service_cidr` is overridden and the flow re-runs
- **THEN** the `/etc/hosts` line reflects the IP derived from the overridden CIDR
