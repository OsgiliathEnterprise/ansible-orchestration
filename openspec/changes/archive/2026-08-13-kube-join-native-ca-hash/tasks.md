## 1. Replace curl+shell with uri module

- [x] 1.1 Replace `ansible.builtin.shell` + `curl -sk` task with `ansible.builtin.uri` to fetch the cluster-info ConfigMap from `https://localhost:6443/api/v1/namespaces/kube-public/configmaps/cluster-info`
- [x] 1.2 Extract kubeconfig string from uri JSON response using native Ansible filters instead of inline Python

## 2. Replace inline Python with native modules

- [x] 2.1 Use `regex_search` / `set_fact` to extract `certificate-authority-data` base64 value from the kubeconfig
- [x] 2.2 Decode base64 CA data using Ansible `b64decode` filter and write PEM to a temporary file via `ansible.builtin.tempfile` + `copy` (or use `slurp`)
- [x] 2.3 Compute DER SHA256 hash with a minimal shell pipeline (`openssl x509 -outform DER | openssl dgst -sha256`) replacing the Python heredoc

## 3. Preserve behavior and clean up

- [x] 3.1 Ensure retry logic (`retries: 5`, `delay: 10`, `until:`) is preserved on the new task(s)
- [x] 3.2 Ensure output variable name remains `current_ca_hash_on_master` with compatible structure for downstream tasks
- [x] 3.3 Clean up any temporary files created during the process
