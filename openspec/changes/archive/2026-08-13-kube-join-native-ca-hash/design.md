## Context

`tasks/kube-install-refresh-join.yml` contains a task that fetches the Kubernetes `cluster-info` ConfigMap via `curl -sk https://localhost:6443/...`, then parses it with an inline Python heredoc to extract the CA certificate, convert to DER format, and compute a SHA256 hash. The rest of the file already uses native Ansible modules (`slurp`, `set_fact`).

## Goals / Non-Goals

**Goals:**
- Replace `shell` + `curl` with `ansible.builtin.uri` (or `get_url`) to fetch the ConfigMap
- Replace inline Python heredoc with native Ansible module chain for JSON parsing, base64 decoding, and hash computation
- Preserve identical output (`current_ca_hash_on_master.stdout`) and retry behavior

**Non-Goals:**
- Changing the overall flow of `kube-install-refresh-join.yml` beyond this single task
- Modifying how the join command is reconstructed (downstream tasks remain unchanged)

## Decisions

**Use `ansible.builtin.uri` over `get_url`:** The `uri` module returns JSON directly when given `return_content: yes`, avoiding an intermediate temp file. It supports `validate_certs: no` to replace `-k`. This is cleaner than writing to `/tmp` and reading back.

**Parse with native Ansible filters instead of Python heredoc:** Use `from_json`, `regex_search`, `b64decode` filters to extract the CA data from the kubeconfig string. For DER conversion and SHA256, keep a minimal shell call using `openssl` (no equivalent built-in filter for certificate DER encoding), but eliminate the Python glue entirely.

**Alternatives considered:**
- Fully native hash computation: Ansible has no built-in module to convert PEM → DER or compute binary SHA256 without calling `openssl`. A small shell task is acceptable here since it replaces a much larger inline-Python block with a simple pipeline.

## Risks / Trade-offs

[Risk] `uri` module may behave differently than `curl -sk` for Kubernetes API responses (e.g., content-type handling, JSON parsing) → Mitigation: use `body_format: json` and handle the response explicitly; test against live cluster during verify phase.

[Risk] The `openssl dgst -sha256` output format differs across platforms (colon-separated vs space-separated hex) → Mitigation: Use `awk '{print $NF}'` or Ansible string splitting to extract just the hex digest, matching current behavior.

[Trade-off] One small shell task remains for DER + hash computation because no pure-Ansible equivalent exists. This is acceptable — the goal was eliminating `curl` and inline Python, not achieving 100% module coverage.
