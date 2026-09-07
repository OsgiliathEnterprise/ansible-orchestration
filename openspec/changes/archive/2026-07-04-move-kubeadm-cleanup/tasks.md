## 1. Move stale kubeadm cleanup to delete-configuration.yml

- [x] 1.1 Move the "clean stale kubeadm state on masters" block from `tasks/kube-install.yml:60-73` into `tasks/delete-configuration.yml` before the `kubeadm reset -f` task (line 14)
- [x] 1.2 Update the task name prefix from "Kube-install" to "Delete-configuration"
- [x] 1.3 Remove the `when: kube_masters_group in group_names` guard (delete-configuration already runs on masters only)
- [x] 1.4 Verify converge passes
