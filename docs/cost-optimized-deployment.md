# Cost-optimized deployment on GCP

Bank of Anthos cannot run entirely within GCP's **always-free** tier — the full stack needs roughly 2 vCPU and 3+ GiB of scheduled pod resources, which exceeds a free `e2-micro` VM. This guide covers the **lowest practical GCP spend** for demos and personal use.

For **$0 ongoing GCP cost**, use local Kubernetes ([minikube](https://minikube.sigs.k8s.io/), [kind](https://kind.sigs.k8s.io/)) or the Cloud Shell tutorial in [`extras/cloudshell/tutorial.md`](../extras/cloudshell/tutorial.md).

## Deployment tiers

| Tier | Kustomize path | Best for |
|------|----------------|----------|
| **Budget** | `kubernetes-manifests/overlays/budget/` | Personal demos, trial credits, minimal monthly bill |
| **Compliant** | `kubernetes-manifests/` (default) | PSS hardening + network boundaries + Secret Manager |
| **Production CI/CD** | `iac/tf-multienv-cicd-anthos-autopilot/` | Multi-env pipeline with Cloud SQL, ASM, Cloud Deploy |

**Do not deploy the full CI/CD Terraform stack** for personal or cost-sensitive use. It provisions three Autopilot clusters, regional Cloud SQL HA, Cloud NAT, ASM/ACM, and continuous build pipelines — typically **$500+/month** if left running.

## What the budget overlay changes

Compared to the default compliant overlay, the budget overlay:

- **Omits loadgenerator** — no continuous synthetic traffic burning CPU
- **Uses ClusterIP for frontend** — no external Load Balancer (~$15–20/month saved)
- **Skips Istio/network-boundaries** — no Anthos Service Mesh requirement
- **Uses ConfigMap DB credentials** — no Secret Manager or Workload Identity setup
- **Disables Cloud Operations export** — `ENABLE_METRICS=false`, `ENABLE_TRACING=false`
- **Lowers resource requests** — smaller Autopilot bill

Trade-off: ConfigMap credentials and no mesh/network policies are acceptable for demos only, not production.

## Quickstart (single GKE Autopilot cluster)

### 1. Create a cluster

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>
export REGION=us-central1

gcloud services enable container.googleapis.com --project="${PROJECT_ID}"

gcloud container clusters create-auto bank-of-anthos \
  --project="${PROJECT_ID}" \
  --region="${REGION}"
```

Use one region and **delete the cluster when you are done** — Autopilot still bills while pods are scheduled, even without a Load Balancer.

### 2. Deploy the budget overlay

```bash
kubectl apply -k kubernetes-manifests/overlays/budget/
```

Wait for pods to become ready:

```bash
kubectl get pods
```

### 3. Access the app

The frontend Service is ClusterIP only. Port-forward from your machine:

```bash
kubectl port-forward svc/frontend 8080:80
```

Open [http://localhost:8080](http://localhost:8080). Demo login: `testuser` / `bankofanthos`.

### 4. Tear down when finished

```bash
# Delete workloads only (keeps cluster)
kubectl delete -k kubernetes-manifests/overlays/budget/

# Delete the entire cluster (stops Autopilot billing)
gcloud container clusters delete bank-of-anthos \
  --project="${PROJECT_ID}" \
  --region="${REGION}"
```

## Expected cost

| Resource | Budget overlay | Left running 24/7 |
|----------|----------------|-------------------|
| GKE Autopilot (8 pods) | Yes | ~$40–80/month |
| External Load Balancer | No | — |
| Cloud SQL | No (in-cluster Postgres) | — |
| Anthos Service Mesh | No | — |
| Secret Manager | No | — |
| Cloud Build / Deploy | No | — |

Using **$300 free trial credits**, a budget deployment left running might last several months. Deleting the cluster when idle is the single biggest savings lever.

## What to avoid for cost savings

| Avoid | Why |
|-------|-----|
| `iac/tf-multienv-cicd-anthos-autopilot/` | 3 clusters + 2 Cloud SQL HA + NAT + pipelines |
| `extras/cloudsql/` | Managed Cloud SQL + larger node pools |
| `extras/asm-multicluster/` | Two clusters + ASM |
| `extras/postgres-hpa/` | HPA scales to many replicas under load |
| Frontend `type: LoadBalancer` | External IP billing |
| Leaving loadgenerator running | Continuous CPU/memory use |

## Local alternatives ($0 GCP)

```bash
# minikube
minikube start --cpus=4 --memory=8192
kubectl apply -k kubernetes-manifests/overlays/budget/
minikube service frontend --url   # or port-forward
```

```bash
# kind
kind create cluster
kubectl apply -k kubernetes-manifests/overlays/budget/
kubectl port-forward svc/frontend 8080:80
```

## Upgrading from budget to compliant

When you need production-style security:

1. Apply Terraform for Secret Manager + Workload Identity (`iac/tf-multienv-cicd-anthos-autopilot/database-secrets.tf`)
2. Switch to the compliant overlay: `kubectl apply -k kubernetes-manifests/`
3. Install Istio/ASM before enabling network-boundaries policies

See [`docs/architecture.md`](architecture.md) for the full deployment tier comparison.
