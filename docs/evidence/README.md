# Evidence from the local Django process

Captured 9 Nov 2026 against `http://127.0.0.1:8000`, where Django was serving this React build. The header in the screenshots reads Django API connected. These files are generated output, not the assessment source.

## Corridor heatmap

The map layer is a canvas in `frontend/src/map/MapPane.tsx`. It draws one radial cell per corridor sample (on the roads and on short perpendicular offsets). Color is the risk band. Shade follows that hour’s wind, rain, and snow depth, so a stronger value is darker and a weak value fades toward the map. The slider only changes which already-fetched hour is painted. Checkpoint dots use driving-arrival risk and stay put.

Seattle to Eugene, departure Tue 10 Nov 2026 8:00 AM Pacific. Open-Meteo cells at hour 0 are mostly Low with a few Moderate. Hour 4 (noon) adds High and one Severe rain cell. The route line stays the arrival-risk color.

- `heatmap-desktop-hour00.png` — 8:00 AM PST
- `heatmap-desktop-hour04.png` — 12:00 PM PST
- `heatmap-mobile-hour00.png`
- `heatmap-mobile-hour04.png`

## Routes

`api-captures.json` is the live `/api/plan` and `/api/assess` summary.

- Chicago to Detroit at 10, 25, and 50 mile spacing. Three Valhalla routes, three different geometry hashes. At 25 miles the route is 282.1 miles with checkpoints including mile 150. That checkpoint’s ETA is 10:21 AM Central, wind 10.3 mph, against an 8:00 AM departure at 7.1 mph.
- Albuquerque to Santa Fe returned two routes. The second is `kind: via` on NM 14, a different geometry hash from I-25, overlap well below a duplicate. The response says a third was not invented.
- Dallas to Oklahoma City returned three routes. Route C is `kind: via` through a real via coordinate, 254 miles versus 206 and 242, with its own geometry hash. It shares a lot of the I-35 corridor with the primary and is still a different Valhalla path, not a copied line.
- Oak Park to Cicero is one 7-mile route. Via search is not used under 30 miles. The note says only one route came back.

## Tests

`pytest.txt` is `python -m pytest -o addopts= -v` from `backend/`. 87 passed.

| File | Tests |
| --- | --- |
| `tests/test_risk.py` | 60, including wind gaps, rain 1.00, snow 3.0, and load cuts at 30000 and 40000 |
| `tests/test_sampling.py` | 7, spacing, remainder, duration ETAs, Chicago offset |
| `tests/test_ranking.py` | 4, partitions, weighted average, ranking, blocked, all blocked |
| `tests/test_assess.py` | 5, arrival sampling, no extrapolation, unknown miles, slider hours |
| `tests/test_units.py` | 4, including snow depth versus water equivalent |
| `tests/test_routes.py` | 4, engine parse, distinctness, city geocoding |
| `tests/test_api.py` | 3, health and a fake end-to-end plan |
