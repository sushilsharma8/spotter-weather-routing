# Headwind

A React and Django desk for comparing up to three driving routes by the weather a truck meets along the way. Weather is read at each checkpoint’s estimated arrival, not once at departure.

Routes come from a public car routing engine. They are **not** certified truck routes and do not apply height, weight, hazmat, or restricted-road rules.

## Run locally

Backend (Python 3.12):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DJANGO_DEBUG=1 python manage.py runserver
```

Frontend, in another shell:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to Django on port 8000. The header should read **Django API connected**.

One process, after a production build:

```bash
cd frontend && npm install && npm run build
cd ../backend && source .venv/bin/activate
SERVE_FRONTEND=1 gunicorn config.wsgi:application --bind 0.0.0.0:8000 --timeout 90
```

Open http://127.0.0.1:8000. Health check: `curl http://127.0.0.1:8000/api/health`.

Docker, from the repo root, on a machine that has Docker:

```bash
docker build -t headwind .
docker run --rm -p 8000:8000 headwind
```

This environment does not have a Docker daemon, so the image was not built here. The same process was run with gunicorn’s equivalent: Django serving the Vite build.

## Vercel

`vercel.json` uses Vercel Services (Beta on all plans; the current `services` key, which replaces `experimentalServices`). It was checked against the published Services, routing, Django, and Vite docs and the `vercel.json` schema at `https://openapi.vercel.sh/vercel.json` on 9 Nov 2026.

- `frontend` service: root `frontend/`, framework `vite`. Its own rewrite sends non-file paths to `/index.html`. Vercel serves built files before that rewrite, so `/assets/*` stays the JS and CSS bundles.
- `backend` service: root `backend/`, framework `django`, runtime `python3.12`, entrypoint `config.wsgi:application` (the `application` object in `config/wsgi.py`, which matches `WSGI_APPLICATION`).
- Public rewrites: `/api/(.*)` goes to the backend and the service still sees `/api/...`, which is what the Django routes expect. Every other path goes to the frontend. The React app keeps calling relative `/api` on the same host.
- `functions["config/wsgi.py"].maxDuration` is 120 seconds, inside the backend service. Fluid Compute’s Hobby ceiling is 300 seconds, so this fits a free account. A Chicago–Detroit plan is a few seconds; the cap leaves room for a slow routing or weather response. Tests are excluded from the function bundle.

No environment variables are required. `DJANGO_DEBUG` defaults off, and `DJANGO_ALLOWED_HOSTS` defaults to `*`. Do not set `VITE_API_BASE`; an absolute API host would skip the same-origin rewrite. This agent did not create a Vercel project or deployment. Deploy the feature-branch commit that contains this file. The local one-process gunicorn command remains valid for machines that are not using Services; on Vercel the frontend service serves the SPA, so Django does not need `frontend/dist`.

## Architecture

```
Browser (React, Leaflet)
  POST /api/plan      geocode, route, checkpoints, corridor sample points
  POST /api/assess    weather at each checkpoint ETA, risk, recommendation
  POST /api/corridor  0–48h forecast for the corridor, used by the slider
        |
Django
  Photon, then Nominatim     place search
  Valhalla auto, then OSRM   driving geometry and duration
  Open-Meteo                 hourly wind, rain, snow depth
```

The plan call returns geometry immediately. Assessment and the corridor forecast then run together. Open-Meteo calls are batched 40 points at a time with at most 3 batches in flight, and successful responses are cached for 20 minutes.

The corridor control is a canvas layer on the map, not a chart. Each sample is a point on or beside the routed roads. At the selected clock hour the layer paints that point’s risk color, lightened when wind, rain, and snow are weak and saturated when they are strong. Dragging the slider repaints those cells from the other hour. Checkpoint dots stay on driving-arrival risk and do not follow the slider.

Miles are the great-circle length of the routed geometry, so the risk categories add up to the route length. Travel time is the engine duration. Checkpoint ETAs walk the engine’s per-edge driving times, scaled so the destination matches that duration. A single truck speed is not assumed.

## Risk rules

Wind (mph), continuous bands, not rounded before comparison:

| Low | Moderate | High | Severe | No travel |
| --- | --- | --- | --- | --- |
| < 25 | [25, 35) | [35, 45) | [45, 55) | ≥ 55 |

Rain (in/hr). Shared endpoints take the higher band. Exactly 1.00 stays Severe.

| Low | Moderate | High | Severe | No travel |
| --- | --- | --- | --- | --- |
| < 0.10 | [0.10, 0.25) | [0.25, 0.50) | [0.50, 1.00] | > 1.00 |

Snow depth (in/hr), not liquid water equivalent. Exactly 3.0 stays Severe.

| Low | Moderate | High | Severe | No travel |
| --- | --- | --- | --- | --- |
| < 0.5 | [0.5, 1) | [1, 2) | [2, 3] | > 3 |

Load, strict greater-than:

- Wind ≥ 55 mph is No Travel at any load.
- Wind in [45, 55) and load above 30,000 lb is No Travel. 30,000 lb does not trigger it.
- Wind in [35, 45) and load above 40,000 lb is Severe. 40,000 lb does not trigger it.

## Assumptions

These are implementation choices. They are not written as rules in the source task.

- Combined risk is the highest of load-adjusted wind, rain, and snow.
- A missing wind, rain, or snow value is Unknown. It is never stored as zero or Low.
- A segment takes the higher risk of its two endpoints, so departure weather and arrival weather both count. The destination is always a checkpoint, including a short remainder.
- Average risk is the mile-weighted mean of Low=1, Moderate=2, High=3, Severe=4, No Travel=5. Unknown miles make the average unavailable.
- Any No Travel or Unknown miles keep the route on the map and out of the ranking. If every route is ineligible, nothing is recommended.
- Eligible routes sort by fewest Severe miles, then fewest High miles, then lowest average risk, then shortest engine time. Differences under 0.0001 miles, 0.000001 risk, or 0.5 seconds are ties. A full tie keeps the earlier route.
- Hourly forecasts are linearly interpolated to the ETA and are not extended past the returned hours. Open-Meteo’s hourly total is treated as that hour’s average intensity.
- Snowfall is converted as depth (cm ÷ 2.54, or inches when the API already says inches). Precipitation water-equivalent is not used as snow depth.
- The 0–48 hour control is a clock offset from departure for the corridor. Checkpoint colors use driving ETAs, which can be a different hour.
- Weather calls are cached for 20 minutes and snapped to 0.01 degree so nearby points share a forecast.
- If the engine returns fewer than three distinct roads, the app says so. It does not copy a route to fill the count. A via point is sent back to the same engine only when a real third geometry is still missing.

## APIs and limits

| Service | Role | Limit |
| --- | --- | --- |
| Valhalla at `valhalla1.openstreetmap.de` | Primary car (`auto`) routes, up to two alternates | Public instance, no key, may throttle or fail |
| OSRM public demo | Fallback car (`driving`) routes | Demo server, not for heavy traffic |
| Open-Meteo forecast | Hourly wind mph, rain inches, snow-depth inches | No key. Non-commercial fair use. Hours outside the model window come back as an error and are shown as Unknown |
| Photon, then Nominatim | Geocoding | No key. Nominatim is only the fallback |
| Esri World Street Map | Basemap | No key. Attribution is on the map |

On 9 Nov 2026 the Open-Meteo forecast window advertised in an error response ran through 24 Nov 2026. A later departure is rejected by the weather service and the routes stay visible as Unknown.

## Tests

```bash
cd backend && python -m pytest
```

87 tests passed against this revision (`python -m pytest` in `backend/`, 0.08s, no network). They cover every wind, rain, snow, and load boundary at the threshold and just beside it, snow-depth versus water-equivalent conversion, remainder checkpoints, duration-based ETAs, the America/Chicago offset, mile partitions, ranking ties, blocked routes, all-blocked routes, and missing forecasts.

A live Chicago → Detroit plan against Valhalla and Open-Meteo returned three routes (about 282, 276, and 294 miles). Category miles matched the geometry length. A March 2027 departure returned Unknown for every mile, Low miles stayed 0, and the recommendation was empty.

## Walkthrough

`WALKTHROUGH.md` is a 5–10 minute recording script. It is meant to be read while using the running app.
