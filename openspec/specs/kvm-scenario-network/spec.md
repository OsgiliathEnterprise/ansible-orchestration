# Kvm Scenario Network

## Purpose

Defines the network topology of the KVM molecule scenario: each platform has a single private network interface, no management NIC is attached, and the control plane reaches each VM through that private network.

## Requirements

### Requirement: No management NIC is attached
The KVM molecule scenario SHALL NOT attach a management NIC to any platform. Each platform's `provider_options` SHALL set `mgmt_attach: false`, so the only interface on each VM is the declared `private_network` interface.

#### Scenario: Single interface per VM
- **WHEN** a KVM scenario platform is brought up on a fresh runner
- **THEN** the VM has exactly one NIC, on the `private_network`
- **THEN** the VM has no NIC on a vagrant-libvirt management network

### Requirement: Control plane reaches VMs through the private network
The KVM scenario's control plane (Ansible's SSH) SHALL reach each VM through the IP of its `private_network` interface, and SHALL NOT depend on a management NIC or a management network IP.

#### Scenario: Fact gathering connects through the private network
- **WHEN** the converge playbook runs the `Facts | gather facts on idm machine` task
- **THEN** the SSH connection to the idm machine uses the idm's `private_network` IP
- **THEN** the connection succeeds without a "No route to host" error
