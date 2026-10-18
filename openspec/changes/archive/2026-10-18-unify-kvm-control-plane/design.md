# Design

## Context

See proposal.md for motivation. Current state of `molecule/kvm/molecule.yml`:

- Four platforms (idm, master, node1, node2), each declaring one interface:
  `type: dhcp`, `network_name: private_network`.
- Driver is `libvirt` (`driver.provider.name: libvirt`).
- `mgmt_attach` is not set, so it takes the vagrant-libvirt default: **`true`**.

vagrant-libvirt behavior (from its documentation):

- With `mgmt_attach` true, every VM additionally gets a NIC on the default
  management network (`vagrant-libvirt`, `192.168.121.0/24`, host bridge
  `virbr1`), independent of any declared interfaces.
- A `type: dhcp` private network defaults to the `172.28.128.0`/24 network
  address (`vagrant-libvirt-private_network`).

Evidence from the CI failure (fresh Travis runner):

```
error target  192.168.121.220   ← "No route to host"
ens6  192.168.121.220           ← mgmt NIC (default mgmt network)
ens7  172.28.128.123            ← private_network interface (declared)
```

The control plane (Ansible SSH via molecule's vagrant driver) binds to the **mgmt**
NIC's IP and cannot route to it on a fresh runner, even though the declared
`private_network` is the interface that is present and expected to be routable.

## Goals / Non-Goals

**Goals:**

- Make the KVM scenario converge on a fresh CI runner (the `Facts | gather facts on
  idm machine` task connects successfully).
- Unify the control plane and data plane onto the single declared `private_network`.
- Attach no management NIC to any KVM platform.

**Non-Goals:**

- No change to the role's runtime tasks, defaults, or other scenarios
  (`default`, `default_noreset_kube` use virtualbox; `parallels` uses parallels —
  neither exposes `mgmt_attach`).
- No change to the private network's subnet or to DHCP vs static addressing.
- No attempt to repair the management network's host-side routing (we remove the
  dependency on it instead).

## Decisions

### Decision 1: Set `mgmt_attach: false` per platform

Add `mgmt_attach: false` to each platform's `provider_options` in
`molecule/kvm/molecule.yml`.

- **Why**: it is the vagrant-libvirt-documented way to suppress the extra mgmt NIC.
  With only the `private_network` NIC remaining, the control plane has exactly one
  IP to bind to — the private one — eliminating the dual-NIC ambiguity.
- **Why per-platform**: `mgmt_attach` is a per-provider (vagrant-libvirt) option, and
  each platform already carries a `provider_options` block (`driver`, `cpus`,
  `memory`, `qemu_use_session`), so `mgmt_attach` slots in naturally. Whether molecule
  renders an *unknown* key like `mgmt_attach` verbatim into the `:libvirt` block is an
  assumption (see **Assumptions**); the `provider_raw_config_args` fallback — already
  used for the 5G `vdb` storage — is the guaranteed path if molecule does not.
- **Alternatives considered**:
  - *Repair the mgmt network's routing* (autostart `vagrant-libvirt`, ensure
    `virbr1` is up): rejected — depends on host libvirt state, is fragile on fresh
    runners, and still leaves the control plane bound to the mgmt IP (the thing we
    cannot route to).
  - *Provider-level `mgmt_attach`*: not clearly supported by molecule's vagrant
    driver (only `driver.provider.name` is exposed at that level); per-platform
    `provider_options` is the verified path.

### Decision 2: Keep DHCP on the private network

Do not switch `private_network` to static IPs.

- **Why**: after each `vagrant up`, molecule reads the live IP from vagrant and
  writes the Ansible inventory, so the control plane always tracks the current IP.
  Static IPs add configuration and collision risk across re-runs for no benefit.
- **Alternative considered**: `type: static` with fixed IPs — rejected as
  unnecessary complexity.

### Decision 3: Rely on the private network's persistence

Do not explicitly create or delete the libvirt network.

- **Why**: the vagrant-libvirt plugin creates `vagrant-libvirt-private_network` on
  first use and does not delete it on `vagrant destroy`, so the scenario reuses the
  same network across cycles with no extra management. This behavior is an
  *assumption* about the plugin (see **Assumptions**), not a spec requirement of this
  change.
- **Risk**: a network that exists but is inactive could break a re-run — covered by
  the verification step that inspects network state.

## Risks / Trade-offs

- **[Root cause not fully confirmed]** The evidence shows the control plane targets
  the mgmt IP and fails to route there; the *exact* reason the mgmt subnet is
  unroutable on a fresh runner (network inactive vs missing host route vs a race) is
  a hypothesis, not a confirmed fact. This change is itself the experiment: if
  `mgmt_attach: false` makes converge pass, the hypothesis is confirmed. The
  verification task runs diagnostics (`virsh net-list`, `ip route`,
  `vagrant ssh-config`) to distinguish the mechanisms if it does not.
- **[DHCP IP changes between runs]** molecule re-reads the live IP after each
  `up`, so the inventory never goes stale.
- **[Removing the mgmt NIC breaks other tooling]** The scenario is self-contained;
  no other scenario or task references the mgmt IP. Verified by inspection.
- **[Shared network across concurrent runs]** Two KVM runs sharing a libvirt URI
  share the same `private_network`; DHCP serves multiple VMs. Not a new risk from
  this change.

## Assumptions

These are relied upon but not guaranteed by this change; each is confirmed (or
falsified) by a verification task in `tasks.md`.

- **The molecule vagrant driver renders `provider_options.mgmt_attach` into the
  generated Vagrantfile's `:libvirt` provider block.** Molecule special-cases a few
  provider options; whether it renders an *unknown* key like `mgmt_attach` verbatim is
  not guaranteed. The fallback is `provider_raw_config_args` (already used for the 5G
  `vdb`), which is rendered verbatim into the provider block. Confirmed by inspecting
  the generated Vagrantfile after `create`.
- **vagrant-libvirt creates `vagrant-libvirt-private_network` on first use and does
  not delete it on `vagrant destroy`**, so a re-converge reuses the same network
  rather than recreating it. Confirmed by `virsh net-list --all` after a destroy.

## Migration Plan

- Single-file change (`molecule/kvm/molecule.yml`); no data or runtime migration.
- Deploy/verify on the CI path — the standalone `test-exec` tox environment:
  `tox -e test-exec -- --scenario-name kvm` (executes `molecule test`, which runs the
  full `test_sequence`: `create`, `prepare`, `converge`, `verify`, then `destroy`).
  This is the exact path that is failing on Travis.
- Rollback: delete the four `mgmt_attach` lines (or the `provider_raw_config_args`
  lines, if that fallback was used).

## Open Questions

- The precise reason the mgmt subnet is unroutable on a fresh runner. Deferrable:
  the fix does not depend on it, and the verification diagnostics will reveal it if
  the fix is insufficient.
