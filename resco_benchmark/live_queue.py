"""Live lane queues and incoming-road traffic for the active SUMO network."""

from __future__ import annotations

import csv
import math
import time
import tkinter as tk
from collections import Counter, defaultdict
from pathlib import Path
from tkinter import ttk
from xml.etree import ElementTree as ET

from resco_benchmark.config.config import config as cfg


DIRECTIONS = ("北", "东北", "东", "东南", "南", "西南", "西", "西北")
DIRECTION_CODES = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
TURN_NAMES = {"l": "Turn left", "s": "Go straight", "r": "Turn right", "t": "U-turn"}
TURN_CODES = {"l": "L", "s": "S", "r": "R", "t": "U"}
TURN_ORDER = ("l", "s", "r", "t")


def network_lane_metadata(network_path):
    root = ET.parse(network_path).getroot()
    edge_lanes = {}
    turns = defaultdict(set)
    for edge in root.findall("edge"):
        if edge.get("function") == "internal":
            continue
        edge_lanes[edge.get("id")] = tuple(
            lane.get("id") for lane in edge.findall("lane")
        )
    for connection in root.findall("connection"):
        edge = connection.get("from")
        lane_index = connection.get("fromLane")
        direction = (connection.get("dir") or "").lower()
        if edge is not None and lane_index is not None and direction in TURN_NAMES:
            turns[f"{edge}_{lane_index}"].add(direction)
    return edge_lanes, turns


def lane_position_names(sumo, lanes):
    """Name physical positions from left to right, using lane geometry."""
    shapes = {lane: sumo.lane.getShape(lane) for lane in lanes}
    starts = [shape[0] for shape in shapes.values() if len(shape) >= 2]
    if not starts:
        return {lane: "" for lane in lanes}
    center_x = sum(point[0] for point in starts) / len(starts)
    center_y = sum(point[1] for point in starts) / len(starts)
    reference = next(shape for shape in shapes.values() if len(shape) >= 2)
    dx = reference[-1][0] - reference[0][0]
    dy = reference[-1][1] - reference[0][1]
    ordered = sorted(lanes, key=lambda lane: -(
        dx * (shapes[lane][0][1] - center_y)
        - dy * (shapes[lane][0][0] - center_x)
    ) if shapes[lane] else 0)
    names = {}
    for index, lane in enumerate(ordered):
        if index == 0:
            position = "leftmost"
        elif index == len(ordered) - 1:
            position = "rightmost"
        elif index == len(ordered) // 2 and len(ordered) % 2:
            position = "middle"
        else:
            position = f"{index + 1} of {len(ordered)} from left"
        names[lane] = position
    return names


def approach_position(shape, distance=25):
    """Find a label position upstream of the traffic-light end of a lane."""
    remaining = distance
    for start, end in zip(reversed(shape[:-1]), reversed(shape[1:])):
        length = math.dist(start, end)
        if remaining <= length and length:
            ratio = remaining / length
            return (end[0] + (start[0] - end[0]) * ratio,
                    end[1] + (start[1] - end[1]) * ratio)
        remaining -= length
    return shape[0]


class LiveQueueDisplay:
    def __init__(self, sumo, output_dir: str) -> None:
        self.sumo = sumo
        self.previous_locations: dict[str, tuple[str, str]] = {}
        self.last_ordinary_edges: dict[str, str] = {}
        self.current_vehicles: dict[str, tuple[str, str, float]] = {}
        self.entered: Counter[str] = Counter()
        self.changed_in: Counter[str] = Counter()
        self.changed_out: Counter[str] = Counter()
        self.approaches: dict[str, dict[str, tuple[str, ...]]] = {}
        self.lane_to_edge: dict[str, str] = {}
        self.lane_labels: dict[str, str] = {}
        self.lane_codes: dict[str, str] = {}
        self.directions: dict[tuple[str, str], int] = {}
        self.positions: dict[tuple[str, str], tuple[float, float]] = {}
        self.poi_ids: dict[tuple[str, str], str] = {}
        self.latest_rows: list[tuple] = []
        self.closed = False
        self.paused = False

        edge_lanes, turns = network_lane_metadata(cfg.network)
        for signal in sorted(sumo.trafficlight.getIDList()):
            approaches: dict[str, tuple[str, ...]] = {}
            for lane in dict.fromkeys(sumo.trafficlight.getControlledLanes(signal)):
                edge = sumo.lane.getEdgeID(lane)
                if edge.startswith(":"):
                    continue
                if edge not in edge_lanes:
                    raise ValueError(f"Incoming road {edge} is missing from {cfg.network}")
                approaches[edge] = edge_lanes[edge]
            if not approaches:
                continue
            self.approaches[signal] = dict(sorted(approaches.items()))
            for edge, lanes in self.approaches[signal].items():
                for lane in lanes:
                    self.lane_to_edge[lane] = edge
                shape = sumo.lane.getShape(lanes[0])
                if len(shape) < 2:
                    continue
                position = approach_position(shape)
                self.positions[(signal, edge)] = position
                dx = position[0] - shape[-1][0]
                dy = position[1] - shape[-1][1]
                self.directions[(signal, edge)] = round(math.atan2(dx, dy) / (math.pi / 4)) % 8
        if not self.approaches:
            raise ValueError("The current SUMO network has no traffic-light controlled lanes")
        self.monitored_edges = set(self.lane_to_edge.values())

        for edge in set(self.lane_to_edge.values()):
            lanes = edge_lanes[edge]
            positions = lane_position_names(sumo, lanes)
            names = {
                lane: " / ".join(TURN_NAMES[turn] for turn in TURN_ORDER if turn in turns[lane])
                or "Unspecified movement"
                for lane in lanes
            }
            codes = {
                lane: "/".join(TURN_CODES[turn] for turn in TURN_ORDER if turn in turns[lane])
                or "?"
                for lane in lanes
            }
            duplicates = Counter(names.values())
            for lane in lanes:
                suffix = f" · {positions[lane]}" if duplicates[names[lane]] > 1 else ""
                self.lane_labels[lane] = names[lane] + suffix
                self.lane_codes[lane] = codes[lane] + (
                    f"@{positions[lane]}" if suffix else ""
                )

        self.output = (Path(output_dir) / "live_queues.csv").open(
            "w", newline="", encoding="utf-8-sig"
        )
        self.writer = csv.writer(self.output)
        self.writer.writerow([
            "time_s", "signal", "approach", "incoming_edge", "lane_id", "lane_label",
            "vehicles_on_road", "sumo_vehicles_on_road", "entered_last_decision",
            "vehicles_on_lane", "moving_on_lane", "stopped_on_lane",
            "lane_changes_in", "lane_changes_out",
        ])

        self.window = tk.Tk()
        self.window.title(f"实时排队监测 · {cfg.map}")
        self.window.geometry("1350x650+30+30")
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        header = tk.Frame(self.window)
        header.pack(fill="x", padx=12, pady=8)
        self.clock = tk.Label(header, text="SUMO 时间 0 秒", font=("Microsoft YaHei", 14, "bold"))
        self.clock.pack(side="left")
        tk.Button(header, text="暂停 / 继续", command=self._toggle_pause).pack(side="right")
        self.delay_ms = tk.IntVar(value=150)
        tk.Scale(header, from_=0, to=1000, resolution=50, orient="horizontal",
                 variable=self.delay_ms, label="每决策步显示延时（毫秒）", length=240).pack(side="right")

        filter_bar = tk.Frame(self.window)
        filter_bar.pack(fill="x", padx=12)
        tk.Label(filter_bar, text="筛选路口 / 道路 / 车道：").pack(side="left")
        self.filter_text = tk.StringVar()
        self.filter_text.trace_add("write", lambda *_: self._render_rows())
        tk.Entry(filter_bar, textvariable=self.filter_text, width=35).pack(side="left")
        self.sum_status = tk.Label(filter_bar, text="道路总数 = 各车道之和")
        self.sum_status.pack(side="right")

        columns = ("signal", "approach", "edge", "lane_label", "road_vehicles",
                   "lane_vehicles", "moving", "stopped", "changed_in", "changed_out", "entered")
        table_frame = tk.Frame(self.window)
        table_frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = ("路口", "进口方位", "进口道路", "车道方向", "道路在途",
                    "车道在途", "行驶中", "静止排队", "变入", "变出", "道路新入")
        widths = (120, 75, 160, 240, 90, 90, 80, 90, 70, 70, 90)
        for column, heading, width in zip(columns, headings, widths):
            self.table.heading(column, text=heading)
            self.table.column(column, width=width, minwidth=65, stretch=True)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        for signal, approaches in self.approaches.items():
            for edge in approaches:
                position = self.positions.get((signal, edge))
                if position is None:
                    continue
                poi_id = f"live_queue_{signal}_{edge}"
                sumo.poi.add(poi_id, *position, color=(0, 0, 0, 0), poiType="-")
                self.poi_ids[(signal, edge)] = poi_id
        self.window.update()

    def _render_rows(self) -> None:
        query = self.filter_text.get().casefold().strip()
        old_rows = self.table.get_children()
        if old_rows:
            self.table.delete(*old_rows)
        for row in self.latest_rows:
            if not query or any(query in str(value).casefold() for value in row[:4]):
                self.table.insert("", "end", values=row)

    def _toggle_pause(self) -> None:
        self.paused = not self.paused

    def _on_close(self) -> None:
        self.closed = True
        self.window.destroy()

    def observe_second(self, count_entries: bool = True) -> None:
        active = set(self.sumo.vehicle.getIDList())
        current = {}
        locations = {}
        for vehicle in active:
            edge = self.sumo.vehicle.getRoadID(vehicle)
            lane = self.sumo.vehicle.getLaneID(vehicle)
            locations[vehicle] = (edge, lane)
            if not edge or edge.startswith(":"):
                continue
            if count_entries and self.last_ordinary_edges.get(vehicle) != edge:
                self.entered[edge] += 1
            self.last_ordinary_edges[vehicle] = edge
            previous = self.previous_locations.get(vehicle)
            if (count_entries and edge in self.monitored_edges and previous
                    and previous[0] == edge and previous[1] != lane):
                self.changed_out[previous[1]] += 1
                self.changed_in[lane] += 1
            if edge in self.monitored_edges:
                if lane not in self.lane_to_edge:
                    raise RuntimeError(f"Vehicle {vehicle} occupies unknown lane {lane} on {edge}")
                current[vehicle] = (edge, lane, self.sumo.vehicle.getSpeed(vehicle))
        self.previous_locations = locations
        self.current_vehicles = current
        for vehicle in self.last_ordinary_edges.keys() - active:
            del self.last_ordinary_edges[vehicle]

    def publish(self, simulation_time: float) -> None:
        if self.closed:
            raise RuntimeError("The live queue display was closed during the simulation")
        self.clock.config(text=f"SUMO 时间 {simulation_time:.0f} 秒 / {cfg.end_time:.0f} 秒")
        road_vehicles = Counter(edge for edge, _, _ in self.current_vehicles.values())
        lane_vehicles = Counter(lane for _, lane, _ in self.current_vehicles.values())
        stopped = Counter(lane for _, lane, speed in self.current_vehicles.values() if speed == 0)
        sumo_road_vehicles = {
            edge: self.sumo.edge.getLastStepVehicleNumber(edge) for edge in self.monitored_edges
        }
        mismatches = [edge for edge in self.monitored_edges
                      if road_vehicles[edge] != sumo_road_vehicles[edge]]
        if mismatches:
            self.sum_status.config(text=f"SUMO 道路计数差异：{len(mismatches)} 条", fg="red")
        else:
            self.sum_status.config(text="道路总数 = 各车道之和（已核对 SUMO）", fg="green")
        self.latest_rows = []
        for signal, approaches in self.approaches.items():
            for edge, approach_lanes in approaches.items():
                direction = self.directions.get((signal, edge))
                direction_name = DIRECTIONS[direction] if direction is not None else "未知"
                entered = self.entered[edge]
                for lane in approach_lanes:
                    moving = lane_vehicles[lane] - stopped[lane]
                    self.writer.writerow([
                        simulation_time, signal, direction_name, edge, lane,
                        self.lane_labels[lane], road_vehicles[edge], sumo_road_vehicles[edge],
                        entered, lane_vehicles[lane], moving, stopped[lane],
                        self.changed_in[lane], self.changed_out[lane],
                    ])
                    self.latest_rows.append((
                        signal, direction_name, edge, self.lane_labels[lane],
                        road_vehicles[edge], lane_vehicles[lane], moving, stopped[lane],
                        self.changed_in[lane], self.changed_out[lane], entered,
                    ))
                poi_id = self.poi_ids.get((signal, edge))
                if poi_id is not None:
                    direction_code = DIRECTION_CODES[direction] if direction is not None else "?"
                    queue = sum(stopped[lane] for lane in approach_lanes)
                    lanes_text = " ".join(
                        f"{self.lane_codes[lane]}:{lane_vehicles[lane]}({stopped[lane]})"
                        for lane in approach_lanes
                    )
                    self.sumo.poi.setType(
                        poi_id, f"{signal} {direction_code} {road_vehicles[edge]}/{queue} {lanes_text}"
                    )
        self.output.flush()
        self.entered.clear()
        self.changed_in.clear()
        self.changed_out.clear()
        self._render_rows()
        self.window.update()
        deadline = time.monotonic() + self.delay_ms.get() / 1000
        while self.paused or time.monotonic() < deadline:
            if self.closed:
                raise RuntimeError("The live queue display was closed during the simulation")
            self.window.update()
            time.sleep(0.03)

    def close(self) -> None:
        self.output.close()
        if not self.closed:
            self.window.destroy()
            self.closed = True
