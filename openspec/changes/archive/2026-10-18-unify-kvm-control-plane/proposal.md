# Proposal

## Why

The KVM molecule scenario fails on a fresh CI runner at `Facts | gather facts on idm
machine` with `ssh: connect to host 192.168.121.220 port 22: No route to host`.
The scenario declares a `private_network` interface per platform, but molecule's
vagrant driver leaves `mgmt_attach` at its default (`true`), so every VM also gets a
management NIC on vagrant-libvirt's default management network (`192.168.121.0/24`).
The control plane (Ansible's SSH) binds to that mgmt NIC's IP, which has no host route
on a fresh runner — while the declared `private_network` (`172.28.128.0/24`) is the
interface that is actually routable. Control plane and data plane are therefore split
across two networks, and the control plane targets the one it cannot reach.

The observable failure above is confirmed by the CI log. The *deeper* reason the mgmt
subnet is unroutable (no libvirt NAT masquerade on a fresh runner) is a hypothesis —
see `design.md`; this fix is itself the confirming experiment.

## What Changes

- Add `mgmt_attach: false` to the `provider_options` of every platform in
  `molecule/kvm/molecule.yml` (idm, master, node1, node2), so no mgmt NIC is attached.
- With only the `private_network` interface remaining, the control plane (Ansible SSH)
  binds to the `private_network` IP, unifying control plane and data plane on a single
  libvirt network that is reliably routable from the host.
- No change to the role's runtime tasks, defaults, or the other scenarios
  (`default`, `default_noreset_kube` use virtualbox; `parallels` uses parallels — none
  of which expose `mgmt_attach`).

## Capabilities

### New Capabilities

- `kvm-scenario-network`: Defines the network topology of the KVM molecule scenario —
  a single `private_network` per platform with no attached management NIC, and the
  control plane reaching each VM through that private network.

### Modified Capabilities

(None — no existing spec-level behavior changes; this is test-infrastructure
topology only.)

## Impact

- `molecule/kvm/molecule.yml` — four `provider_options` blocks gain `mgmt_attach: false`.
- CI (Travis, KVM profile) — the `test-exec` profile runs the standalone `test-exec`
  tox environment (`tox -e test-exec -- --scenario-name kvm`), which executes
  `molecule test` on the `kvm` scenario; the control plane now SSHes via the
  `private_network` IP instead of the mgmt IP.
- No runtime impact on the role itself; no new dependencies.
