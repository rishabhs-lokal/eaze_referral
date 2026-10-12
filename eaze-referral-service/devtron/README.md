# Devtron configuration

What is actually pasted into Devtron's UI, kept here so it is reviewable, diffable, and
recoverable. Devtron is the source of truth for what is *running*; this directory is the source
of truth for what it is *supposed* to be. If you change a value in the UI, change it here too —
otherwise this becomes confidently wrong, which is worse than absent.

## `deployment-template-tier-1000.yaml`

Devtron's Deployment custom chart, edited for this service. Everything not listed below is the
chart default, left alone deliberately.

| Changed | From | To | Why |
|---|---|---|---|
| `ContainerPort[0].port` | `8080` | `8000` | uvicorn binds 8000 — see the pod's own `Uvicorn running on http://0.0.0.0:8000` |
| probe `Path` ×3 | `""` | `/healthz` | an empty path checks nothing |
| probe `port` ×3 | `8080` | `8000` | same as above |
| probe `scheme` | `""` | `HTTP` | |
| `StartupProbe.failureThreshold` | `3` | `12` | ~135s for the DB pool to come up; the default gives 50s, tight against a cold or cross-AZ database |
| `MinReadySeconds` | `60` | `20` | with real probes, 60 only slows rollouts |
| `resources.limits.memory` | `50Mi` | `256Mi` | **measured 74 MiB idle** — the default OOM-kills the pod during startup |
| `resources.limits.cpu` | `0.05` | `0.5` | 50 millicores cannot start a Python process in reasonable time |
| `resources.requests` | `10Mi` / `0.01` | `128Mi` / `0.1` | |
| `ingress.enabled` | `false` | `true` | ClusterIP alone is unreachable from a user's browser, which is where this API is called from |
| `ingress.hosts[0].host` | example | `eaze-referral1000.eazeapp.com` | `{project}-{app}.{domain}` |
| `ingress.tls[0].secretName` | — | `eaze-referral1000-tls` | `{project}-{app}-tls` |

Still to confirm against your cluster:

- `ingress.className` is left `""`. With no default ingress class the Ingress object is created
  and silently never routed.
- `eaze-referral1000-tls` must exist or be issued by cert-manager. If your other apps annotate
  the ingress for that, add the same annotation under `ingress.annotations`.

## The two config objects

Both named `eaze-referral1000`, both mounted as **Environment Variable** (not Data Volume — this
service reads env vars; mounting as files leaves every key unset and the pod starts up looking
healthy while unable to reach the database or Redash).

- **ConfigMap** — the 20 keys in `../k8s/tier-1000/10-configmap.yaml`
- **Secret** — 4 keys, template in `../k8s/tier-1000/11-secret.example.yaml`

## One host, three places

`eaze-referral1000.eazeapp.com` appears in:

1. `ingress.hosts[0].host` here
2. `PUBLIC_BASE_URL` in the ConfigMap
3. `EXPO_PUBLIC_API_BASE_URL` in the web build

A mismatch in (3) is the nastiest: the page loads perfectly and every API call fails.

## Migrations

`dbMigrationConfig.enabled` stays `false`. Migrations run as a **pre-deployment stage** in the CD
pipeline — `alembic upgrade head`, same image, same ConfigMap and Secret attached.

Post-deployment, or omitted, means pods serve traffic against a schema with no
`referral_verifications` table. This is the single biggest difference from the `kubectl` path,
where `scripts/deploy.sh` ran the migration Job to completion before rolling the Deployment.
