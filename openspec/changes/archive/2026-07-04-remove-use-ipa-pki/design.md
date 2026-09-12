## Context

`use_ipa_pki` is defined in `defaults/main.yml` as `False`, but all 3 molecule converge files override it to `True`. The variable adds dead conditional branches.

## Goals / Non-Goals

**Goals:**
- Remove `use_ipa_pki` variable and all conditional gates

**Non-Goals:**
- Changing IPA PKI behavior

## Decisions

- IPA PKI tasks run unconditionally on `kube_masters_group` hosts (existing gate)

## Risks / Trade-offs

- None — no scenario sets `use_ipa_pki` to `False`
