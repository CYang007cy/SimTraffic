"""Build a reproducible nine-signal grid from RESCO's grid4x4 network."""

from __future__ import annotations

import csv
import os
import random
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path


HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent / "grid4x4" / "grid4x4.net.xml"
SIGNALS = [f"{col}{row}" for col in "ABC" for row in range(3)]
RENAMED_BOUNDARIES = {
    **{f"{col}3": f"top{i}" for i, col in enumerate("ABC")},
    **{f"D{row}": f"right{row}" for row in range(3)},
}
BOUNDARIES = {
    **{f"left{row}": f"A{row}" for row in range(3)},
    **{f"right{row}": f"C{row}" for row in range(3)},
    **{f"bottom{i}": f"{col}0" for i, col in enumerate("ABC")},
    **{f"top{i}": f"{col}2" for i, col in enumerate("ABC")},
}
OLD_NODES = set(SIGNALS) | set(RENAMED_BOUNDARIES) | {
    f"left{row}" for row in range(3)
} | {f"bottom{i}" for i in range(3)}
FOCAL_CENTER = ["A0", "B0", "B1", "C1", "C2"]
FOCAL_OUTER = ["A0", "A1", "A2", "B2", "C2"]
SEED = 1


def write_xml(name: str, root: ET.Element) -> None:
    ET.indent(root, space="    ")
    ET.ElementTree(root).write(HERE / name, encoding="utf-8", xml_declaration=True)


def node_name(old: str) -> str:
    return RENAMED_BOUNDARIES.get(old, old)


def make_plain_network() -> tuple[dict[str, tuple[str, str]], set[tuple[str, str]]]:
    source = ET.parse(REFERENCE).getroot()
    nodes = ET.Element("nodes")
    for junction in source.findall("junction"):
        old = junction.get("id")
        if old not in OLD_NODES:
            continue
        new = node_name(old)
        attrs = {
            "id": new,
            "x": junction.get("x"),
            "y": junction.get("y"),
            "type": junction.get("type") if new in SIGNALS else "dead_end",
        }
        if new in SIGNALS:
            attrs["tl"] = new
        else:
            attrs["fringe"] = "outer"
        ET.SubElement(nodes, "node", attrs)
    write_xml("grid3x3.nod.xml", nodes)

    edges = ET.Element("edges")
    old_to_new = {}
    endpoints = {}
    for edge in source.findall("edge"):
        old_from, old_to = edge.get("from"), edge.get("to")
        if old_from not in OLD_NODES or old_to not in OLD_NODES:
            continue
        new_from, new_to = node_name(old_from), node_name(old_to)
        if new_from not in SIGNALS and new_to not in SIGNALS:
            continue
        edge_id = new_from + new_to
        lanes = edge.findall("lane")
        ET.SubElement(
            edges,
            "edge",
            {
                "id": edge_id,
                "from": new_from,
                "to": new_to,
                "priority": edge.get("priority", "-1"),
                "numLanes": str(len(lanes)),
                "speed": lanes[0].get("speed"),
            },
        )
        old_to_new[edge.get("id")] = edge_id
        endpoints[edge_id] = (new_from, new_to)
    assert len(endpoints) == 48
    write_xml("grid3x3.edg.xml", edges)

    connections = ET.Element("connections")
    tls = ET.Element("tlLogics")
    for logic in source.findall("tlLogic"):
        if logic.get("id") in SIGNALS:
            tls.append(ET.fromstring(ET.tostring(logic)))

    allowed = set()
    count = 0
    for connection in source.findall("connection"):
        if connection.get("tl") not in SIGNALS:
            continue
        old_from, old_to = connection.get("from"), connection.get("to")
        if old_from not in old_to_new or old_to not in old_to_new:
            continue
        common = {
            "from": old_to_new[old_from],
            "to": old_to_new[old_to],
            "fromLane": connection.get("fromLane"),
            "toLane": connection.get("toLane"),
        }
        ET.SubElement(connections, "connection", common)
        ET.SubElement(
            tls,
            "connection",
            {
                **common,
                "tl": connection.get("tl"),
                "linkIndex": connection.get("linkIndex"),
            },
        )
        allowed.add((common["from"], common["to"]))
        count += 1
    assert count == 9 * 36
    write_xml("grid3x3.con.xml", connections)
    write_xml("grid3x3.tll.xml", tls)
    return endpoints, allowed


def netconvert_binary() -> str:
    binary = shutil.which("netconvert")
    if binary:
        return binary
    try:
        import sumo
    except ImportError as exc:
        raise RuntimeError("Set SUMO_HOME or install eclipse-sumo") from exc
    suffix = ".exe" if os.name == "nt" else ""
    return str(Path(sumo.SUMO_HOME) / "bin" / f"netconvert{suffix}")


def compile_network() -> None:
    command = [
        netconvert_binary(),
        "--node-files", str(HERE / "grid3x3.nod.xml"),
        "--edge-files", str(HERE / "grid3x3.edg.xml"),
        "--connection-files", str(HERE / "grid3x3.con.xml"),
        "--tllogic-files", str(HERE / "grid3x3.tll.xml"),
        "--output-file", str(HERE / "grid3x3.net.xml"),
        "--no-turnarounds",
        "--junctions.corner-detail", "5",
        "--junctions.limit-turn-speed", "5.5",
        "--offset.disable-normalization",
    ]
    subprocess.run(command, check=True)


def shortest_path(start: str, end: str, rng: random.Random) -> list[str]:
    if start == end:
        return [start]
    queue = deque([[start]])
    seen = {start}
    while queue:
        path = queue.popleft()
        col, row = ord(path[-1][0]) - ord("A"), int(path[-1][1])
        neighbors = [f"{chr(ord('A') + x)}{y}" for x, y in (
            (col - 1, row), (col + 1, row), (col, row - 1), (col, row + 1)
        ) if 0 <= x < 3 and 0 <= y < 3]
        rng.shuffle(neighbors)
        for neighbor in neighbors:
            if neighbor == end:
                return path + [neighbor]
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(path + [neighbor])
    raise RuntimeError(f"No path from {start} to {end}")


def make_routes(endpoints: dict[str, tuple[str, str]], allowed: set[tuple[str, str]]) -> None:
    rng = random.Random(SEED)
    entries = list(BOUNDARIES)
    trips = []
    for origin in entries:
        count = 180 if origin == "left0" else 84
        for index in range(count):
            if origin == "left0" and index < 160:
                destination = "top2"
                family = "center" if index % 2 == 0 else "outer"
                path = FOCAL_CENTER if family == "center" else FOCAL_OUTER
            else:
                destination = rng.choice([x for x in entries if x != origin])
                family = "background"
                path = shortest_path(BOUNDARIES[origin], BOUNDARIES[destination], rng)
            route = [origin + path[0]]
            route.extend(a + b for a, b in zip(path, path[1:]))
            route.append(path[-1] + destination)
            assert all(edge in endpoints for edge in route)
            assert all((a, b) in allowed for a, b in zip(route, route[1:]))
            trips.append((round(rng.uniform(0, 3500), 2), origin, destination, family, route))

    trips.sort(key=lambda trip: trip[0])
    routes = ET.Element("routes")
    with (HERE / "grid3x3_od.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["vehicle_id", "depart", "origin", "destination", "route_family", "route_edges"])
        for index, (depart, origin, destination, family, route) in enumerate(trips):
            vehicle_id = str(index)
            vehicle = ET.SubElement(routes, "vehicle", {"id": vehicle_id, "depart": f"{depart:.2f}"})
            ET.SubElement(vehicle, "route", {"edges": " ".join(route)})
            writer.writerow([vehicle_id, f"{depart:.2f}", origin, destination, family, " ".join(route)])
    assert len(trips) == 1104
    write_xml("grid3x3.rou.xml", routes)


def main() -> None:
    endpoints, allowed = make_plain_network()
    compile_network()
    make_routes(endpoints, allowed)
    (HERE / "grid3x3.sumocfg").write_text(
        '<configuration>\n'
        '  <input>\n'
        '    <net-file value="grid3x3.net.xml"/>\n'
        '    <route-files value="grid3x3.rou.xml"/>\n'
        '  </input>\n'
        '  <time>\n'
        '    <begin value="0"/>\n'
        '    <end value="3600"/>\n'
        '  </time>\n'
        '</configuration>\n',
        encoding="utf-8",
    )
    print("Built grid3x3: 9 signals, 48 directed edges, 1104 vehicles")


if __name__ == "__main__":
    main()
