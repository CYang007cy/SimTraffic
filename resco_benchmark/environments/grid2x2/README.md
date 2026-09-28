# grid2x2 environment

This four-signal scenario is derived from the neighboring `grid3x3` network. Columns A–B run west to east; rows 0–1 run south to north. The eight `left*`, `right*`, `bottom*`, and `top*` nodes are external entry and exit points, not controlled intersections.

```text
A1 -- B1
 |     |
A0 -- B0
```

The network has 24 directed roads, three lanes per road, 300 m between adjacent junction centers, and a 13.89 m/s road speed limit. Each signal retains the eight green-phase patterns and three-second yellow transitions from `grid3x3`. RESCO's `FIXED` controller uses `[4, 2, 4, 2, 4, 2, 4, 2]` decisions per green phase, with a five-second decision interval. The SUMO-native signal program in `grid2x2.net.xml` has its own phase durations; use RESCO for signal-control experiments.

## Files

- `grid2x2.net.xml`: compiled SUMO network.
- `grid2x2.rou.xml`: 4,608 vehicles departing during a six-hour simulation.
- `grid2x2.sumocfg`: SUMO GUI configuration for seconds 0–21,600.
- `grid2x2_od.csv`: vehicle ID, departure, origin, destination, route family, and initial route.
- `inspect_queues.py`: halted-vehicle snapshot for the eight signal-controlled movement lanes at each junction.
- `grid2x2.{nod,edg,con,tll}.xml`: plain network source files.
- `generate.py`: deterministic generator; reads `../grid3x3/grid3x3.net.xml` and uses SUMO `netconvert`.

Demand uses seed 1. Each hour has 768 vehicles: 180 at the `left0` entrance and 84 at each of the other seven entrances. Departures are randomized independently within each hour. Over six hours, 4,608 vehicles depart. Of the `left0` vehicles, 160 per hour travel to `top1`, split equally between two routes of 1,118.4 m each:

```text
via_B0: left0A0 A0B0 B0B1 B1top1
via_A1: left0A0 A0A1 A1B1 B1top1
```

The other 608 vehicles per hour use randomized boundary OD pairs and shortest-hop paths. Routes are fixed; navigation and rerouting are not yet implemented. The OD metadata is retained for that later experiment. There is no unique center junction in a 2×2 grid, so a branch-specific signal perturbation can target `B0` or `A1`.

The generated demand is reproducible with seed 1. RESCO currently starts SUMO with `--random True`, so controlled comparisons of signal policies also need a fixed SUMO simulation seed.

## Run on Windows PowerShell

From this directory, with the `simtraffic-sumo` environment installed:

```powershell
$env:SUMO_HOME = "D:\anaconda3\envs\simtraffic-sumo\Lib\site-packages\sumo"
& "$env:SUMO_HOME\bin\sumo-gui.exe" -c grid2x2.sumocfg
```

To run RESCO's fixed-time baseline, change to `RESCO\resco_benchmark` and run:

```powershell
& "D:\anaconda3\envs\simtraffic-sumo\python.exe" main.py "@grid2x2" "@FIXED" libsumo:False gui:True episodes:1 save_console_log:False
```

To show queues live in the **same RESCO-controlled simulation**, add `live_queues:True`:

```powershell
& "D:\anaconda3\envs\simtraffic-sumo\python.exe" main.py "@grid2x2" "@FIXED" libsumo:False gui:True live_queues:True episodes:1 save_console_log:False
```

This opens the SUMO GUI with 16 approach labels and a searchable live table. Each 5-second control decision refreshes both views. The table names the three incoming lanes `Turn right`, `Go straight`, and `Turn left`, and shows current lane vehicles, moving vehicles, stationary vehicles, and lane changes. It includes all 12 lanes at each junction, including right-turn lanes; the former straight/left-only display showed eight. Its pause button stops advancing the simulation; the delay slider adjusts display speed. SUMO's current lane and edge positions determine road membership, so a vehicle crossing a signal appears on its downstream road when it enters that road; it enters that lane's stationary count only at zero speed. The run retains `live_queues.csv` in its RESCO results ZIP archive. Opening `grid2x2.sumocfg` directly does not activate the RESCO controller or this live display. See [LIVE_QUEUES.md](../../LIVE_QUEUES.md) for other networks and CSV fields.

To regenerate the network and demand, run `python generate.py` from this directory with the same environment. The generator overwrites its generated XML and CSV files.

To inspect a queue snapshot at simulation time 900 seconds, run:

```powershell
& "D:\anaconda3\envs\simtraffic-sumo\python.exe" inspect_queues.py --time 900
```

Change `--time` to any integer from 1 to 21,600. The script starts a separate SUMO simulation using the signal program in `grid2x2.net.xml`. It reports vehicles with speed below 0.1 m/s on the eight phase-controlled movement lanes (lane indices 1 and 2), grouped by each of the four inbound roads. The four right-turn lanes (index 0) are omitted. This is a snapshot under SUMO-native control, not the result of a RESCO `@FIXED` run.

This environment adapts `grid3x3`, which in turn adapts RESCO's `grid4x4` data, and carries the same CC BY-NC-SA 4.0 license; see `LICENSE`.
