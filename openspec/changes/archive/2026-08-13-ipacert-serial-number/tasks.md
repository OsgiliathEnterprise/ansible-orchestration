## 1. Update delete-ipa-cleanup.yml

- [x] 1.1 Add stat-based checks for each IPA-signed certificate file before attempting revocation
- [x] 1.2 Extract serial number from admin cert (`{{ kube_credential_folder }}/kubeadm.crt`) using `openssl x509 -serial`
- [x] 1.3 Extract serial number from API server cert (`{{ kubernetes_certificates_path }}/apiserver.crt`)
- [x] 1.4 Extract serial number from kubelet client cert (`{{ kubernetes_certificates_path }}/apiserver-kubelet-client.crt`)
- [x] 1.5 Extract serial number from front-proxy cert (`{{ kubernetes_certificates_path }}/front-proxy-client.crt`)
- [x] 1.6 Update ipacert revocation calls to use `serial_number` instead of relying solely on `certificate_name`