"""Show stopped vehicles on the eight signal-controlled lanes at each junction."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import sumo
import traci


HERE = Path(__file__).resolve().parent
END_TIME = 21600


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--time", type=int, default=900, help="snapshot time in seconds")
    args = parser.parse_args()
    if not 0 < args.time <= END_TIME:
        parser.error(f"--time must be between 1 and {END_TIME}")

    os.environ.setdefault("SUMO_HOME", str(sumo.SUMO_HOME))
    binary = Path(sumo.SUMO_HOME) / "bin" / ("sumo.exe" if os.name == "nt" else "sumo")
    traci.start([str(binary), "-c", str(HERE / "grid2x2.sumocfg"), "--no-step-log"])
    try:
        traci.simulationStep(args.time)
        print(f"Time: {traci.simulation.getTime():.0f} s; halted vehicles (speed < 0.1 m/s)")
        for signal in traci.trafficlight.getIDList():
            lanes = sorted({
                lane for lane in traci.trafficlight.getControlledLanes(signal)
                if lane.rsplit("_", 1)[-1] in {"1", "2"}
            })
            assert len(lanes) == 8, (signal, lanes)
            print(f"{signal}:")
            for edge in sorted({traci.lane.getEdgeID(lane) for lane in lanes}):
                edge_lanes = [lane for lane in lanes if traci.lane.getEdgeID(lane) == edge]
                counts = [traci.lane.getLastStepHaltingNumber(lane) for lane in edge_lanes]
                details = ", ".join(f"{lane}={count}" for lane, count in zip(edge_lanes, counts))
                print(f"  {edge}: {sum(counts)} ({details})")
    finally:
        traci.close()


if __name__ == "__main__":
    main()
