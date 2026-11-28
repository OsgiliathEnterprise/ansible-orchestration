# Transient Shuttle Hygiene

## Purpose

Guarantees that the role's transient download and staging shuttles (CA fetches, CSR/enrollment staging, profile scratch, tool tarballs, gate anchors) use per-run unique temporary paths created only when a gated block actually needs them, so steady-state reconverge is untouched by shuttle work, change reporting stays truthful, concurrent host-side fetches cannot collide, and no shuttle artifact survives a successful converge.

## Requirements

### Requirement: Shuttle artifacts use per-run unique paths

Every transient file or directory a task writes to temporarily download or stage content during converge SHALL be created with a per-run unique name (tempfile generation), never at a fixed folder or fixed file-name path, so that concurrent delegated fetches against a shared host cannot overwrite or read each other's artifacts.

#### Scenario: Concurrent joins fetch CAs without collision

- **WHEN** two worker nodes execute their join-time CA fetches on the shared idm host at the same time
- **THEN** each fetch writes to and reads only its own per-run artifact
- **AND** neither node can observe the other node's partially written CA file

#### Scenario: Steady state exposes no fixed shuttle path

- **WHEN** converge completes for any path of the role (fresh, drift, or no-op reconverge)
- **THEN** no artifact was ever created at a legacy fixed shuttle path (`/run/ipa-ca-fetch`, `/tmp/kube-node-ca*.crt`, `/tmp/kube-api-gate-anchor.crt`, `/tmp/kube-admin-enroll.*`, `/tmp/ipa_*_ca_profile.cfg`, `/tmp/helm-*` tarball or `/tmp/linux-*/` extraction dir)

### Requirement: Tempfiles are minted only when their block is needed

Temporary-file creation and removal tasks SHALL live exclusively inside blocks gated on state or drift checks that evaluate to skip when the system already matches the desired state. A steady-state reconverge SHALL execute no tempfile create/delete task and SHALL report zero changed tasks from shuttle work.

#### Scenario: No-op reconverge mints no tempfiles

- **WHEN** the role converges against an already-converged, up-to-date cluster (CAs matching IPA, nodes joined, profiles present, required CLIs installed)
- **THEN** every tempfile task in the shuttle flows is skipped
- **AND** the reconverge reports zero changed tasks from these flows

#### Scenario: Drift reconverge mints tempfiles truthfully

- **WHEN** converge runs while a gate is open (e.g. an IPA CA rotated, a node not yet joined, or a profile missing)
- **THEN** the gated block mints its tempfile(s), performs the fetch/staging, removes them, and those tasks report changed because real work happened

### Requirement: CA fetch shuttle runs only on fingerprint drift

The master's CA fetch-and-install shuttle (CA #1 `kubernetes-ca` and CA #2 `kubeclusteradm`) SHALL execute only when the master's installed copy is missing or its certificate fingerprint differs from the IPA-published CA, as determined by a read-only comparison. The downloads SHALL report change truthfully rather than being blanket-suppressed.

#### Scenario: Installed CAs match the published CAs

- **WHEN** the master's installed CA #1 and CA #2 fingerprints equal the fingerprints of the CAs published by IPA
- **THEN** the fetch block (tempfile, `ipa ca-show` downloads, slurps, installs) is skipped
- **AND** the read-only fingerprint probe is the only task that executed, reporting no change

#### Scenario: Installed CA drifted or is missing

- **WHEN** an installed CA copy is absent or its fingerprint differs from the published CA
- **THEN** the fetch block runs, the master-side install reports changed, and the fetched content matches the published CA byte for byte after decoding

### Requirement: Shuttles leave no residue after converge

A successful converge SHALL leave no transient shuttle artifact on any host: each gated block removes the tempfiles it minted, and no credential-bearing or certificate scratch file remains in `/tmp` or a volatile `/run` scratch directory. A pre-existing legacy fixed-path artifact left by an earlier version SHALL be swept to a no-change steady state.

#### Scenario: Successful converge leaves hosts clean

- **WHEN** any converge completes successfully (fresh or reconverge)
- **THEN** no shuttle artifact remains on idm or the kube hosts: no CA fetch copy, no `kubeAdministrators`-family profile `.cfg` scratch, no admin enrollment `.csr`/`.crt` pair, no gate anchor file, no helm tarball or extraction directory

#### Scenario: Legacy fixed-path artifact is swept

- **WHEN** a converge runs on hosts left by a previous version that still contains a legacy fixed shuttle path (e.g. `/run/ipa-ca-fetch`)
- **THEN** the converge removes it (reporting changed once) and a further reconverge reports no change
