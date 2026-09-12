## 1. Remove use_ipa_pki from defaults

- [x] 1.1 Remove `use_ipa_pki: False` from `defaults/main.yml`
- [x] 1.2 Verify converge passes

## 2. Remove use_ipa_pki gates from main.yml

- [x] 2.1 Remove `use_ipa_pki | bool` condition from "Setup IPA PKI infrastructure" include (`tasks/main.yml:37`)
- [x] 2.2 Remove `use_ipa_pki | bool` condition from "Setup IPA PKI certificates" include (`tasks/main.yml:55`)
- [x] 2.3 Verify converge passes

## 3. Remove use_ipa_pki from molecule converge files

- [x] 3.1 Remove `use_ipa_pki: True` from `molecule/default/converge.yml`
- [x] 3.2 Remove `use_ipa_pki: True` from `molecule/default_noreset_kube/converge.yml`
- [x] 3.3 Remove `use_ipa_pki: True` from `molecule/kvm/converge.yml`
- [x] 3.4 Verify converge passes
