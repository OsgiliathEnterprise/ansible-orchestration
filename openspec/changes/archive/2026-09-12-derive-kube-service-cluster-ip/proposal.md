# Derive Kube Service Cluster IP

## Why

`tasks/ipa-kubernetes-ca.yml` adds a `/etc/hosts` entry on the IPA server for the Dogtag reachability check with a **hard-coded** service cluster IP (`10.96.0.1 {{ orchestration_host_hostname }}`), while every other consumer of the service cluster IP in the role derives it from `kube_service_cidr` (`kube-install.yml` certSANs, the DNS zone/A/PTR records in the same file, `ipa-api-server.yml` SANs). If `kube_service_cidr` is overridden from its default `10.96.0.0/12`, the `/etc/hosts` entry points at the wrong IP and the Dogtag reachability check for the real service IP fails.

## What Changes

- Replace the hard-coded `10.96.0.1` in the `Ipa-kubernetes-ca | add kube service cluster IP to IPA server hosts for Dogtag reachability check` task (`tasks/ipa-kubernetes-ca.yml`) with the first usable IP of the service CIDR: `(kube_service_cidr | default('10.96.0.0/12')) | ansible.utils.next_nth_usable(1)` — the exact idiom already used by the six other consumers.
- Behavior under the default CIDR is byte-identical (`10.96.0.1`); behavior becomes correct under any overridden CIDR.

## Capabilities

### New Capabilities

- `kube-ca-reachability`: DNS and `/etc/hosts` reachability support for the Kubernetes CA certificate flow on the IPA server — every IP used for the Dogtag/FreeIPA reachability checks is derived from `kube_service_cidr`, never hard-coded.

### Modified Capabilities

(none)

## Impact

- `tasks/ipa-kubernetes-ca.yml` — one line (the `line:` value of the `/etc/hosts` lineinfile task).
- No new dependencies, no variable changes (`kube_service_cidr` already exists in `defaults/main.yml`).
- No converge behavior change under the default CIDR.
