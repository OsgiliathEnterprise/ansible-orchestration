# Tasks

## 1. Configuration change

- [x] 1.1 Add `mgmt_attach: false` to the `provider_options` of all four platforms
      (idm, master, node1, node2) in `molecule/kvm/molecule.yml`. Verify the file
      still parses as valid YAML and that each of the four `provider_options` blocks
      contains `mgmt_attach: false` (e.g., `python3 -c "import yaml; yaml.safe_load(open('molecule/kvm/molecule.yml'))"` plus a grep for the key).

## 2. Verification on the KVM scenario

- [x] 2.1 Verify the molecule driver honors `provider_options.mgmt_attach`: after
      `create` (or `test`), locate the Vagrantfile molecule generated for the `kvm`
      scenario (under `~/.cache/molecule/tcharl.ansible_orchestration/kvm/` or the
      scenario directory) and assert the `:libvirt` provider block contains
      `mgmt_attach = false`. **If it does not**, molecule did not render the unknown
      key — switch to the fallback: add `mgmt_attach = false` to each platform's
      `provider_raw_config_args` (the mechanism already used for the 5G `vdb` storage)
      and re-verify. (Confirms design.md Assumptions.)
      _Verified via static source analysis (2026-10-18): the `molecule_vagrant`
      template loops over every `provider_options` key and renders
      `libvirt.<option> = ruby_format(value)`; `ruby_format(false)` → `false`.
      The `provider_raw_config_args` fallback is therefore not needed. The literal
      runtime artifact check (inspect the generated Vagrantfile after `create`) is
      deferred to the Linux/CI run._
- [ ] 2.2 Run the CI path — the standalone `test-exec` tox environment:
      `tox -e test-exec -- --scenario-name kvm` (executes `molecule test`, which runs
      the full `test_sequence` including `converge` and `verify`). Verify the
      `Facts | gather facts on idm machine` task completes (SSH connects via the
      `private_network` IP with no "No route to host") and that converge and verify
      succeed.
- [ ] 2.3 Verify the single-NIC topology: after `vagrant up`, run
      `vagrant ssh <idm-vm> -c "ip -br addr"` and verify only the `private_network`
      interface exists (no management-NIC interface on a management network).
- [ ] 2.4 Verify the persistence assumption holds: after `vagrant destroy`, run
      `virsh net-list --all` and confirm the `vagrant-libvirt-private_network` libvirt
      network still exists and is active, and that a subsequent `vagrant up`
      re-attaches the VMs to that same network. (Confirms the design.md assumption;
      it is not a spec requirement of this change.)

## 3. Fallback diagnostics (only if 2.2 still fails)

- [ ] 3.1 If converge still fails after the config change, run diagnostics to identify
      the mechanism: `virsh net-list --all` (network state), `ip route` on the host
      (routes to the private and mgmt subnets), and `vagrant ssh-config` (which IP
      molecule binds the control plane to). Record the findings and update the
      Open Questions section of `design.md` with the confirmed mechanism.
