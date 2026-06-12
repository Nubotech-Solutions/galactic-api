# Galactic Logistics API

A small, self-contained FastAPI service that simulates the operational API of a deep-space
logistics and command station. It exposes crew, cargo, shipment, trade, and classified fleet
data behind a three-tier clearance model.

It was built as a rich, realistic **demo target for OpenAPI → MCP integration** (NTS-MCP-Buddy):
the endpoints, descriptions, and role-based access control are designed so an AI agent can
navigate the API across clearance levels and chain multi-step queries the way a human operator
would. There is no external database — data lives in a mutable in-memory store seeded from
hardcoded baseline data in [main.py](main.py), so writes persist for the life of the process
and can be wiped via the hidden reset endpoint (see below).

## Features

- **Read + write endpoints** across 6 domains (station, crew, cargo, shipments, trade, fleet),
  backed by a mutable in-memory store seeded from hardcoded baseline data
- **Role-based access control** with three clearance levels enforced per-endpoint and per-record
- **Rich OpenAPI spec** — every endpoint and field is documented with descriptions and examples,
  so the generated schema (and any MCP tools derived from it) is self-explanatory
- **Single file, no database** — easy to read, run, and deploy
- **Containerized** and auto-deployed to Google Cloud Run

## Clearance model

All endpoints except `/v1/whoami` require a Bearer token. The token *is* the role — there is no
login step. Pass it in the `Authorization` header:

```
Authorization: Bearer <your-clearance-token>
```

| Level | Role | Access |
|---|---|---|
| 1 | Deckhand | Station status & systems, crew roster, cargo manifest |
| 2 | Logistics Officer | + Crew details, cargo details, shipments, trade manifests |
| 3 | Sector Admiral | + Fleet orders, missions, and all classified records |

A few records (e.g. shipment `SH-004`, trade manifest `TM-003`, cargo `C-777` / `C-999`) are
**Admiral-classified**: they are hidden from level-2 list responses and return `403` on their
detail endpoints below level 3.

- `401 Unauthorized` — token missing or unrecognized
- `403 Forbidden` — token valid, but clearance level too low for this endpoint or record

> The demo clearance tokens are defined in `ROLE_HIERARCHY` at the top of [main.py](main.py).
> They are intentionally **not** published in the OpenAPI spec. Hand them to API consumers
> out-of-band.

## Endpoints

| Method | Path | Min level | Description |
|---|---|---|---|
| GET | `/v1/whoami` | public | Caller's role and clearance level |
| GET | `/v1/station/status` | 1 | Overall station health |
| GET | `/v1/station/systems` | 1 | All subsystems with health % |
| GET | `/v1/crew` | 1 | Crew roster (name, role, duty status) |
| GET | `/v1/crew/{crew_id}` | 2 | Full crew member record |
| GET | `/v1/cargo/manifest` | 1 | Cargo index (ID + name) |
| GET | `/v1/cargo/{cargo_id}` | 2 | Full cargo item details |
| GET | `/v1/shipments` | 2 | All convoys with status & ETA |
| GET | `/v1/shipments/{shipment_id}` | 2 | Full convoy details |
| GET | `/v1/trade/manifests` | 2 | All trade contracts |
| GET | `/v1/trade/manifests/{manifest_id}` | 2 | Full trade contract |
| GET | `/v1/fleet/orders` | 3 | Classified strategic orders |
| GET | `/v1/fleet/missions` | 3 | All fleet missions |
| GET | `/v1/fleet/missions/{mission_id}` | 3 | Full mission briefing |
| PATCH | `/v1/station/systems/{system_id}` | 1 | Update a subsystem's status/health/notes |
| PATCH | `/v1/crew/{crew_id}/duty-status` | 2 | Set a crew member On/Off Duty |
| PATCH | `/v1/cargo/{cargo_id}/inspection` | 2¹ | Update a cargo item's inspection status |
| POST | `/v1/shipments` | 2 | Create a new convoy (server assigns `SH-NNN`) |
| PATCH | `/v1/shipments/{shipment_id}` | 2¹ | Update a convoy's status/eta/delay/cargo/notes |
| DELETE | `/v1/shipments/{shipment_id}` | 3 | Cancel and remove a convoy |
| PATCH | `/v1/trade/manifests/{manifest_id}` | 2¹ | Update a trade contract's status/notes |
| PATCH | `/v1/fleet/missions/{mission_id}` | 3 | Update a mission's status/notes |

Write endpoints mirror the read clearance of their entity. Deletes are Admiral-only (level 3).
¹ Mutating an Admiral-classified record (`SH-004`, `TM-003`, `C-777`, `C-999`) requires level 3,
mirroring the read rules.

Interactive docs are served at `/docs` (Swagger UI) and `/redoc`; the raw schema is at
`/openapi.json`. There is also an unlisted `/health` check.

### Hidden reset endpoint

> **Repo-only docs — intentionally absent from the OpenAPI spec.** This endpoint is *not*
> in `/openapi.json`, `/docs`, or `/redoc`, and is documented **only here in this README** so
> that AI/MCP consumers built from the spec never discover or call it.

`POST /v1/internal/reset` restores the in-memory store to its seed baseline, discarding
everything written via the POST/PATCH/DELETE endpoints. It is gated by a dedicated secret
header, **independent of the clearance tokens**:

```bash
curl -X POST -H "X-Reset-Key: <reset-key>" http://localhost:8080/v1/internal/reset
```

The key is read from the `RESET_KEY` environment variable (default `reset-outpost-gamma` for
local runs). A missing or wrong key returns `403`. Hand the real key out out-of-band, like the
clearance tokens.

In deployment, the [GitHub Actions workflow](.github/workflows/deploy.yml) injects `RESET_KEY`
into the Cloud Run service from a repository secret named **`RESET_KEY`** (set it under
*Settings → Secrets and variables → Actions*). Make sure that secret is populated — if it's
unset, the workflow passes an empty value and an empty `X-Reset-Key` header would match.

## Running locally

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Then open http://localhost:8080/docs.

### With Docker

```bash
docker build -t galactic-api .
docker run -p 8080:8080 galactic-api
```

## Example requests

```bash
# Identity check (no token needed)
curl http://localhost:8080/v1/whoami

# Level 1
curl -H "Authorization: Bearer <deckhand-token>" http://localhost:8080/v1/station/systems

# Level 2 — cargo detail (403 at level 1)
curl -H "Authorization: Bearer <logistics-token>" http://localhost:8080/v1/cargo/C-098

# Level 3 — classified shipment (hidden / 403 below level 3)
curl -H "Authorization: Bearer <admiral-token>" http://localhost:8080/v1/shipments/SH-004

# Write — set a crew member off duty (level 2)
curl -X PATCH -H "Authorization: Bearer <logistics-token>" -H "Content-Type: application/json" \
  -d '{"duty_status": "Off Duty"}' http://localhost:8080/v1/crew/CR-004/duty-status

# Write — create a new convoy (level 2); server returns the assigned SH-NNN id
curl -X POST -H "Authorization: Bearer <logistics-token>" -H "Content-Type: application/json" \
  -d '{"convoy_name": "Convoy Vega", "origin": "Outpost Gamma", "destination": "Waystation Delta", "cargo_ids": ["C-098"]}' \
  http://localhost:8080/v1/shipments

# Delete — cancel a convoy (Admiral only; 403 below level 3)
curl -X DELETE -H "Authorization: Bearer <admiral-token>" http://localhost:8080/v1/shipments/SH-006
```

In Swagger UI, click **Authorize**, paste a token, and every "Try it out" call carries it.
Re-authorize with a lower-level token to watch the same endpoints start returning `403`.

## Deployment

Pushing to `main` triggers the [GitHub Actions workflow](.github/workflows/deploy.yml), which
deploys to **Google Cloud Run** (source-to-service) using Workload Identity Federation:

- Service: `galactic-api-public`
- Region: `europe-west4`
- Flags: `--allow-unauthenticated --port=8080 --memory=256Mi`

Get the live URL with:

```bash
gcloud run services describe galactic-api-public --region europe-west4 --format "value(status.url)"
```

## Project layout

```
main.py                       # the entire app: RBAC, data, models, endpoints
requirements.txt              # fastapi, uvicorn
Dockerfile                    # python:3.11-slim, runs as non-root
.github/workflows/deploy.yml  # Cloud Run deployment
```
