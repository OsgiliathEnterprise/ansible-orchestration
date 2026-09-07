## Why

The `use_ipa_pki` boolean was a transitional toggle during IPA PKI integration. All molecule scenarios and production use set it to `True`. Removing it eliminates dead conditional branches and simplifies the codebase.

## What Changes

- Remove `use_ipa_pki: False` from `defaults/main.yml`
- Remove `use_ipa_pki | bool` gates from `tasks/main.yml`
- Remove `use_ipa_pki: True` from all molecule converge files

## Capabilities

### Modified Capabilities
- `ipa-pki-bootstrap`: remove `use_ipa_pki` gating; IPA PKI always runs on masters

## Impact

- `defaults/main.yml`: remove variable
- `tasks/main.yml`: remove 2 conditional gates
- `molecule/default/converge.yml`, `molecule/default_noreset_kube/converge.yml`, `molecule/kvm/converge.yml`: remove var
