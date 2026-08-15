## 1. Add kubelet-client cert signing test

- [x] 1.1 Add `test_apiserver_kubelet_client_crt_signed_by_kubernetes_ca` — checks `/etc/kubernetes/pki/apiserver-kubelet-client.crt` issuer contains "kubernetes-ca"

## 2. Add front-proxy-client cert signing test

- [x] 2.1 Add `test_front_proxy_client_crt_signed_by_kubernetes_ca` — checks `/etc/kubernetes/pki/front-proxy-client.crt` issuer contains "kubernetes-ca"

## 3. Verify kubernetes-ca chains to IPA root CA

- [x] 3.1 Add `test_kubernetes_ca_signed_by_ipa_root_ca` — fetches IPA root CA via Dogtag HTTP endpoint, verifies chain with `openssl verify`
