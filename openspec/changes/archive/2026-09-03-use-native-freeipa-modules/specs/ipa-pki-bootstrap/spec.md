## ADDED Requirements

### Requirement: Admin user principal is created via native ipauser module
The `kubeclusteradm` IPA user principal SHALL be created via the `freeipa.ansible_freeipa.ipauser` Ansible module and SHALL NOT use a shell-based `ipa user-add` command. The principal SHALL be created with first name `kube`, last name `ClusterAdmin`, the configured admin email address, and the realm password.

#### Scenario: Principal is created when missing
- **WHEN** the role runs on the IPA server and the `kubeclusteradm` principal does not exist
- **THEN** the principal is created via the `freeipa.ansible_freeipa.ipauser` module with first name `kube`, last name `ClusterAdmin`, the configured admin email address, and the realm password

#### Scenario: Principal creation is idempotent
- **WHEN** the role runs on the IPA server and the `kubeclusteradm` principal already exists
- **THEN** no error is raised and the task reports that the principal is already present

#### Scenario: No shell user-add for admin principal
- **WHEN** the role runs
- **THEN** no shell-based `ipa user-add` command is executed to create the `kubeclusteradm` principal
