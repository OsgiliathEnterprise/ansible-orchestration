## 1. Replace helm delete commands with kubernetes.core.helm

- [x] 1.1 Replace `helm delete istio-ingress -n istio-system` with `kubernetes.core.helm` (name=istio-ingress, namespace=istio-system, state=absent)
- [x] 1.2 Replace remaining 3 helm delete tasks (istio-egress, istiod, istio-base) using same pattern

## 2. Replace kubectl drain with kubernetes.core.k8s_drain

- [x] 2.1 Replace `kubectl drain` command with `kubernetes.core.k8s_drain` module
- [x] 2.2 Map flags: --force → force:true, --ignore-daemonsets → ignore_daemonsets:true, --delete-emptydir-data → delete_emptydir_data:true, --timeout=800s → grace_period_seconds:800

## 3. Replace kubectl delete node with kubernetes.core.k8s

- [x] 3.1 Replace `kubectl delete node --all` with `kubernetes.core.k8s` module (kind=Node, state=absent)
