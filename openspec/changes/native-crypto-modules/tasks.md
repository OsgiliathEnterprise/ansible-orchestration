## 1. Replace serial number extraction in delete-ipa-cleanup.yml

- [x] 1.1 Replace `openssl x509 -serial` for admin cert with `community.crypto.x509_certificate_info` (path=..., register=_cleanup_admin_cert_info, use `_cleanup_admin_cert_info.cert.serial_number`)
- [x] 1.2 Replace remaining 3 serial extraction tasks (apiserver, kubelet-client, front-proxy) using same pattern

## 2. Replace CSR generation in admin-user.yml

- [x] 2.1 Replace `openssl req -new` command with `community.crypto.openssl_csr` module
- [x] 2.2 Map parameters: privatekey_path, cn=kubeclusteradm, country_name=..., organization_name=clusterAdministrators

## 3. Verify output compatibility

- [x] 3.1 Ensure serial number format matches what IPA expects (hex string vs integer)
- [x] 3.2 Run verify to confirm tests still pass
