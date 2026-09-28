# Live traffic and queue display

Start a RESCO experiment with `gui:True live_queues:True`. For example, from the
`RESCO/resco_benchmark` directory in PowerShell:

```powershell
& "D:\anaconda3\envs\simtraffic-sumo\python.exe" -m resco_benchmark.main "@grid3x3" "@FIXED" "libsumo:False" "gui:True" "live_queues:True" "episodes:1" "save_console_log:False"
```

Replace `@grid3x3` with another configured RESCO network, such as `@grid2x2`.
The network must have traffic-light-controlled lanes. The monitor discovers the
actual signals, incoming roads, and lanes from the running SUMO connection.

The bundled `grid4x4` directory currently has `grid4x4_1.rou.xml` rather than
the route file expected by its extra-flow generator. To use that existing route
directly, run:

```powershell
& "D:\anaconda3\envs\simtraffic-sumo\python.exe" -m resco_benchmark.main "@grid4x4" "@FIXED" "route:grid4x4_1.rou.xml" "flow:0" "libsumo:False" "gui:True" "live_queues:True" "episodes:1" "save_console_log:False"
```

Here `flow:0` skips RESCO's extra-flow generation; vehicles still come from
`grid4x4_1.rou.xml`.

The searchable window shows one row for **every lane** on each incoming road,
including lanes not controlled by the signal. It names lanes by their permitted
connections: `Turn left`, `Go straight`, `Turn right`, `U-turn`, or a combined
label for a mixed lane. If several lanes share the same label, their physical
left-to-right position distinguishes them. The raw SUMO lane ID remains in the
CSV for traceability. The approach column describes the side from which the
road approaches the signal, inferred from lane geometry.

Each row displays the current road and lane vehicle counts, moving vehicles,
stationary vehicles, lane changes into and out of that lane since the previous
decision, and new arrivals on the road. A vehicle counts as stationary only
when its reported speed is exactly zero. The road count is the sum of all its
lane counts, and the window checks it against SUMO's own road count. Road-level
values repeat on that road's lane rows; do not sum those repeated CSV columns.

At every RESCO decision step, the same values refresh in the window and SUMO
GUI labels. A GUI label shows the road total/stationary total followed by each
lane's turn code and `vehicles(stationary)` count. `L`, `S`, `R`, and `U` mean
left, straight, right, and U-turn; a slash marks a mixed lane. The pause button
pauses simulation advance; the slider changes the delay between decisions.

`live_queues.csv` uses one row per time, signal, and lane. RESCO may place this
file in the run's results ZIP archive. Vehicles are added to a downstream road
when SUMO reports that road as their current road. Lane changes are detected
each SUMO second; a vehicle moves from the old lane's current count to the new
lane's count. Stationary vehicles leave the stopped count when they resume.
