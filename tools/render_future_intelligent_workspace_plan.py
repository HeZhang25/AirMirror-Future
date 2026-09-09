"""Render a presentation-friendly top view without adding GUI geometry."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from airmirror_future.scene.serialization import load_scene
from airmirror_future.experiments.xr_route import load_route_experiment


def main() -> None:
    root = Path(__file__).parents[1]
    scene = load_scene(root / "scenes" / "future_intelligent_workspace_demo.json")
    route = load_route_experiment(root / "scenes" / "future_intelligent_workspace_route.json")
    figure, axis = plt.subplots(figsize=(13.0, 9.0), dpi=180)
    axis.set_facecolor("#0b1220")
    figure.patch.set_facecolor("#0b1220")
    for wall in scene.walls:
        color = "#dbe4f0" if "boundary" in wall.id else "#fbbf24"
        width = 2.2 if "boundary" in wall.id else 3.4
        axis.plot([wall.start.x, wall.end.x], [wall.start.y, wall.end.y], color=color, lw=width)
    for obstacle in scene.obstacles:
        axis.add_patch(Rectangle(
            (obstacle.min_corner.x, obstacle.min_corner.y),
            obstacle.max_corner.x - obstacle.min_corner.x,
            obstacle.max_corner.y - obstacle.min_corner.y,
            facecolor="#92400e", edgecolor="#f59e0b", alpha=0.78, lw=1.4,
        ))
    tx = scene.transmitter().position
    rx = scene.receiver().position
    axis.scatter([tx.x], [tx.y], s=120, color="#ef4444", edgecolor="white", zorder=8)
    axis.scatter([rx.x], [rx.y], s=120, color="#22c55e", edgecolor="white", zorder=8)
    axis.text(tx.x + 0.15, tx.y + 0.18, "TX", color="white", weight="bold")
    axis.text(rx.x + 0.15, rx.y + 0.18, "RX", color="white", weight="bold")
    ris_colors = ["#a78bfa", "#38bdf8"]
    for ris, color in zip(scene.ris_surfaces, ris_colors):
        axis.scatter([ris.position.x], [ris.position.y], marker="s", s=170, color=color, edgecolor="white", zorder=8)
        axis.text(ris.position.x + 0.15, ris.position.y + 0.18, ris.id, color=color, weight="bold")
        normal_end = (ris.position.x + 0.9 * ris.normal[0], ris.position.y + 0.9 * ris.normal[1])
        axis.arrow(ris.position.x, ris.position.y, normal_end[0] - ris.position.x, normal_end[1] - ris.position.y,
                   color=color, width=0.018, head_width=0.18, length_includes_head=True, zorder=7)
    points = route.route.waypoints
    axis.plot([point.x for point in points], [point.y for point in points], color="#38bdf8", lw=2.3, alpha=0.9, zorder=6)
    for index, point in enumerate(points, start=1):
        axis.scatter([point.x], [point.y], s=42, color="#0ea5e9", edgecolor="#e0f2fe", zorder=9)
        axis.text(point.x + 0.1, point.y - 0.28, str(index), color="#e0f2fe", fontsize=8, zorder=10)
    labels = ((2.0, 1.0, "TX / workbench zone"), (1.0, 7.9, "Meeting area"), (4.5, 8.5, "Lab / experiment"),
              (8.7, 8.5, "East collaboration"), (4.5, 0.45, "Connector corridor"))
    for x, y, label in labels:
        axis.text(x, y, label, color="#cbd5e1", fontsize=9, alpha=0.9)
    axis.set_xlim(-0.4, scene.room_size.x + 0.4)
    axis.set_ylim(-0.4, scene.room_size.y + 0.4)
    axis.set_aspect("equal")
    axis.set_xlabel("x (m)", color="#cbd5e1")
    axis.set_ylabel("y (m)", color="#cbd5e1")
    axis.tick_params(colors="#94a3b8")
    axis.grid(color="#334155", alpha=0.35, lw=0.6)
    axis.set_title("Future Intelligent Workspace · dual Future RIS", color="white", fontsize=16, weight="bold", pad=14)
    axis.text(0.01, 1.01, "Scene v1 walls/obstacles only · blue route · arrows show RIS outward normals",
              transform=axis.transAxes, color="#94a3b8", fontsize=9, va="bottom")
    figure.tight_layout()
    output = root / "results" / "prototypes" / "future_intelligent_workspace_top_view.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, facecolor=figure.get_facecolor())
    print(output)


if __name__ == "__main__":
    main()
