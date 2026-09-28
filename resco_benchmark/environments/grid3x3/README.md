# grid3x3 environment

This controlled nine-signal scenario is derived from RESCO's `grid4x4` network. Columns A–C run west to east; rows 0–2 run south to north. `B1` is the center signal. The 12 `left*`, `right*`, `bottom*`, and `top*` nodes are external entry and exit points, not controlled intersections.

```text
A2 -- B2 -- C2
 |     |     |
A1 -- B1 -- C1
 |     |     |
A0 -- B0 -- C0
```

The network has 48 directed roads, three lanes per road, approximately 300 m between adjacent junction centers, and a 13.89 m/s road speed limit. Each signal retains the eight green-phase patterns and three-second yellow transitions from `grid4x4`. RESCO's `FIXED` controller uses `[4, 2, 4, 2, 4, 2, 4, 2]` decisions per green phase, with a five-second decision interval. The SUMO-native signal program in `grid3x3.net.xml` has its own phase durations; use RESCO for signal-control experiments.

## Files

- `grid3x3.net.xml`: compiled SUMO network.
- `grid3x3.rou.xml`: 1,104 vehicles departing during the first 3,500 seconds of a one-hour simulation.
- `grid3x3.sumocfg`: SUMO GUI configuration for seconds 0–3,600.
- `grid3x3_od.csv`: vehicle ID, departure, origin, destination, route family, and initial route.
- `grid3x3.{nod,edg,con,tll}.xml`: plain network source files.
- `generate.py`: deterministic generator; reads the neighboring `grid4x4/grid4x4.net.xml` and uses SUMO `netconvert`.

Demand uses seed 1. There are 180 vehicles at the `left0` entrance and 84 at each of the other 11 entrances. Of the `left0` vehicles, 160 travel to `top2`, split equally between two equal-hop initial routes:

```text
center: left0A0 A0B0 B0B1 B1C1 C1C2 C2top2
outer:  left0A0 A0A1 A1A2 A2B2 B2C2 C2top2
```

The other 944 vehicles use randomized boundary OD pairs and shortest-hop paths. The route file contains fixed routes. It does not implement vehicle navigation or rerouting; the explicit OD metadata is retained for that later experiment.

The generated demand is reproducible with seed 1. RESCO currently starts SUMO with `--random True`, so controlled comparisons of signal policies also need a fixed SUMO simulation seed.

## Run on Windows PowerShell

From this directory, with the `simtraffic-sumo` environment installed:

```powershell
$env:SUMO_HOME = "D:\anaconda3\envs\simtraffic-sumo\Lib\site-packages\sumo"
& "$env:SUMO_HOME\bin\sumo-gui.exe" -c grid3x3.sumocfg
```

To run RESCO's fixed-time baseline, change to `RESCO\resco_benchmark` and run:

```powershell
& "D:\anaconda3\envs\simtraffic-sumo\python.exe" main.py "@grid3x3" "@FIXED" libsumo:False gui:True episodes:1 save_console_log:False
```

To regenerate the network and demand, run `python generate.py` from this directory with the same environment. The generator overwrites its generated XML and CSV files.

This environment adapts the `grid4x4` data and carries the same CC BY-NC-SA 4.0 license; see `LICENSE`.
