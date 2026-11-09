# Headwind walkthrough (5–10 minutes)

Record against a running app whose header says **Django API connected**. Use Chicago → Detroit, Central time, and the default next-morning departure unless that morning is outside the forecast.

## 0:00 What this is

Headwind compares driving routes by the weather the truck drives into. Say clearly: these are car-profile routes from Valhalla or OSRM. They are not certified truck routes and do not apply height, weight, or road restrictions. Travel time is the engine’s driving time, not an hours-of-service plan.

## 0:45 Inputs

Show origin, destination, departure, and the timezone control. Point at the sentence that the clock is Central wall time, not the browser zone. Show load weight and the note that 30,000 lb and 40,000 lb do not themselves trigger the load steps. Set spacing to 25 miles. Leave load at 25,000 lb for the first plan, then mention you will raise it.

## 1:30 Three real routes

Click **Chicago → Detroit**. The map draws the roads before the colors arrive, with the line “Sampling weather at each checkpoint’s estimated arrival.” When the result settles, point at three different lines: the primary and two engine alternates, with different miles and times. Open one card and read the provider (`valhalla` or `osrm`) and the road name. If a third distinct road is ever missing, show the note instead of pretending there is a third.

## 3:00 Checkpoint arrival, not departure

Select route A and open a checkpoint that is not mile 0. Read the ETA, the elapsed driving time, and the wind, rain, and snow-depth numbers. Say that mile 0 uses the departure hour and later checkpoints use later hours. Mention snow is depth in inches per hour, not melted water.

## 4:00 Recommendation

Read the recommended route and the reasons. Open the ranking table: fewest Severe miles, then fewest High miles, then average risk (Low=1 … No Travel=5, weighted by miles), then travel time. On a calm forecast the weather columns tie and the shorter drive wins. That is the rule, not a missing score.

## 5:15 Corridor slider

Drag the 0–48 hour slider. The heading clock and the wind number change. The sparkline cursor moves along the fetched hourly series. Say the teal bar is only the driving window of the selected route, while the slider can show later corridor weather. Checkpoint colors do not follow the slider. They follow arrival time. If the whole corridor stays green, the forecast is in the Low band. The numbers are still changing.

## 6:30 Missing forecast

Edit the trip and set a departure months ahead, or any time the forecast cannot cover. Submit again. The roads and the corridor turn Unknown, the banner says the samples were not treated as Low, average risk is unavailable, and the panel says no route is recommended. Do not describe that as a safe route.

## 7:30 Load and assumptions

Set the load above 40,000 lb and say what would change if wind were in the 35–45 mph band: that checkpoint becomes Severe. Above 30,000 lb, wind from 45 up to 55 mph becomes No Travel. Open **Assumptions and scoring** and name two choices that the source task did not spell out: higher-risk ties on shared rain and snow endpoints, and dropping any route with No Travel or Unknown miles instead of ranking it.

## 8:30 Close

Mention `python -m pytest` in `backend/` for the boundary tests, and that the map, slider, and blocked-forecast states were checked in the browser against the live engines.
