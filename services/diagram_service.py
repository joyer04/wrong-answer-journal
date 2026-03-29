"""
services/diagram_service.py
============================
Server-side diagram generation using matplotlib.

Supported diagram types:
  - function_graph : Cartesian coordinate system with one or more functions
  - triangle       : Labeled triangle with optional right-angle mark
  - circle         : Circle with radius label and optional marked points
  - number_line    : Number line with closed/open point markers

Each function returns a base64-encoded PNG string.
"""

from __future__ import annotations

import base64
import io
import math
from typing import Any, Optional

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")  # Non-interactive backend (no display needed)

# ---------------------------------------------------------------------------
# Shared style constants
# ---------------------------------------------------------------------------
PRIMARY   = "#2563eb"   # blue
SECONDARY = "#dc2626"   # red
GREEN     = "#059669"
PURPLE    = "#7c3aed"
PALETTE   = [PRIMARY, SECONDARY, GREEN, PURPLE, "#f59e0b", "#10b981"]

plt.rcParams.update(
    {
        "font.family":    "DejaVu Sans",
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "figure.facecolor":   "white",
        "axes.facecolor":     "white",
    }
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_diagram_base64(spec: dict[str, Any]) -> str:
    """Generate a diagram from *spec* and return a base64-encoded PNG."""
    dtype = spec.get("type", "none")
    if dtype == "function_graph":
        fig = _function_graph(spec)
    elif dtype == "triangle":
        fig = _triangle(spec)
    elif dtype == "circle":
        fig = _circle(spec)
    elif dtype == "number_line":
        fig = _number_line(spec)
    else:
        raise ValueError(f"Unknown diagram type: {dtype!r}")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ---------------------------------------------------------------------------
# function_graph
# ---------------------------------------------------------------------------

def _function_graph(spec: dict) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(6, 5))

    x_range = spec.get("x_range", [-6, 6])
    y_range = spec.get("y_range", None)
    functions = spec.get("functions", [])
    points    = spec.get("points", [])
    title     = spec.get("title", "")

    x = np.linspace(x_range[0], x_range[1], 600)

    # Safe namespace for eval — only numpy math
    _ns: dict = {k: getattr(np, k) for k in dir(np) if not k.startswith("_")}
    _ns["__builtins__"] = {}

    for i, func in enumerate(functions):
        expr  = func.get("expr", "x")
        label = func.get("label", expr)
        color = func.get("color", PALETTE[i % len(PALETTE)])
        try:
            y = eval(expr, {"x": x, **_ns})  # noqa: S307
            # Mask large discontinuities (asymptotes)
            with np.errstate(invalid="ignore"):
                dy = np.abs(np.diff(y, prepend=y[0]))
                y  = np.where(dy > 50, np.nan, y)
            ax.plot(x, y, color=color, linewidth=2.5, label=label, zorder=3)
        except Exception as exc:
            print(f"[diagram] Cannot plot '{expr}': {exc}")

    # Axes through origin
    ax.axhline(0, color="black", linewidth=0.9, zorder=0)
    ax.axvline(0, color="black", linewidth=0.9, zorder=0)
    ax.grid(True, alpha=0.25, linewidth=0.5)

    # Mark special points
    for pt in points:
        px = float(pt.get("x", 0))
        py = float(pt.get("y", 0))
        lbl = pt.get("label", f"({px}, {py})")
        ax.scatter([px], [py], color=SECONDARY, s=55, zorder=6)
        ax.annotate(lbl, (px, py), xytext=(6, 8),
                    textcoords="offset points", fontsize=8.5, color=SECONDARY)

    ax.set_xlim(x_range)
    if y_range:
        ax.set_ylim(y_range)
    ax.set_xlabel("x", fontsize=11, labelpad=4)
    ax.set_ylabel("y", fontsize=11, labelpad=4, rotation=0)

    if len(functions) > 1:
        ax.legend(fontsize=9, framealpha=0.85)

    if title:
        ax.set_title(title, fontsize=12, pad=10)

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# triangle
# ---------------------------------------------------------------------------

def _triangle(spec: dict) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(5.5, 5))

    verts = spec.get("vertices", {"A": [0, 0], "B": [4, 0], "C": [2, 3]})
    A = np.array(verts.get("A", [0, 0]), dtype=float)
    B = np.array(verts.get("B", [4, 0]), dtype=float)
    C = np.array(verts.get("C", [2, 3]), dtype=float)

    # Draw triangle
    triangle = plt.Polygon([A, B, C], fill=True, facecolor="#eff6ff",
                            edgecolor=PRIMARY, linewidth=2.2)
    ax.add_patch(triangle)

    # Right-angle mark
    right_at = spec.get("right_angle_at")
    if right_at and right_at in verts:
        _draw_right_angle(ax, verts, right_at)

    # Vertex labels — offset outward from centroid
    centroid = (A + B + C) / 3.0
    for name, pt in zip(("A", "B", "C"), (A, B, C)):
        direction = pt - centroid
        norm = np.linalg.norm(direction)
        offset = (direction / norm * 0.35) if norm else np.array([0, 0.35])
        ax.text(pt[0] + offset[0], pt[1] + offset[1], name,
                fontsize=13, fontweight="bold", ha="center", va="center",
                color="#1e3a5f")

    # Side labels
    side_mid = {
        "AB": (A + B) / 2, "BC": (B + C) / 2, "CA": (C + A) / 2,
        "BA": (A + B) / 2, "CB": (B + C) / 2, "AC": (C + A) / 2,
    }
    labels = spec.get("labels", {})
    for side, lbl in labels.items():
        if side in side_mid:
            mid = side_mid[side]
            ax.text(mid[0], mid[1], lbl, fontsize=10, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                              edgecolor="#c7d2fe", alpha=0.95))

    _equal_axes_with_margin(ax, [A, B, C], margin=0.8)
    ax.set_aspect("equal")
    ax.axis("off")

    title = spec.get("title", "")
    if title:
        ax.set_title(title, fontsize=12, pad=8)

    fig.tight_layout()
    return fig


def _draw_right_angle(ax: plt.Axes, verts: dict, vertex: str) -> None:
    """Draw a small square at *vertex* to indicate a right angle."""
    pts = {k: np.array(v, dtype=float) for k, v in verts.items()}
    names = list(pts.keys())
    v0 = pts[vertex]
    others = [pts[n] for n in names if n != vertex]
    if len(others) < 2:
        return
    d1 = others[0] - v0
    d2 = others[1] - v0
    s = min(np.linalg.norm(d1), np.linalg.norm(d2)) * 0.12
    d1n = d1 / np.linalg.norm(d1) * s
    d2n = d2 / np.linalg.norm(d2) * s
    sq = plt.Polygon(
        [v0 + d1n, v0 + d1n + d2n, v0 + d2n],
        fill=False, edgecolor=PRIMARY, linewidth=1.2,
    )
    ax.add_patch(sq)


# ---------------------------------------------------------------------------
# circle
# ---------------------------------------------------------------------------

def _circle(spec: dict) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(5.5, 5.5))

    center = np.array(spec.get("center", [0, 0]), dtype=float)
    radius = float(spec.get("radius", 3))
    title  = spec.get("title", "")
    pts    = spec.get("points", [])

    # Draw circle
    circle = plt.Circle(center, radius, fill=True, facecolor="#eff6ff",
                        edgecolor=PRIMARY, linewidth=2.5)
    ax.add_patch(circle)

    # Center dot
    ax.plot(*center, "o", color="#1e3a5f", markersize=4, zorder=4)

    # Radius line + label
    ax.plot([center[0], center[0] + radius], [center[1], center[1]],
            color=PRIMARY, linewidth=1.2, linestyle="--", alpha=0.7)
    ax.text(center[0] + radius / 2, center[1] + radius * 0.08,
            f"r = {radius}", ha="center", fontsize=10, color=PRIMARY)

    # Points on circle
    for pt in pts:
        ang = math.radians(float(pt.get("angle_deg", 0)))
        px  = center[0] + radius * math.cos(ang)
        py  = center[1] + radius * math.sin(ang)
        ax.plot(px, py, "o", color=SECONDARY, markersize=7, zorder=5)
        lbl = pt.get("label", "")
        if lbl:
            offset = np.array([math.cos(ang), math.sin(ang)]) * radius * 0.18
            ax.text(px + offset[0], py + offset[1], lbl,
                    fontsize=9, ha="center", va="center", color=SECONDARY)

    margin = radius * 1.35
    ax.set_xlim(center[0] - margin, center[0] + margin)
    ax.set_ylim(center[1] - margin, center[1] + margin)
    ax.set_aspect("equal")
    ax.axis("off")

    if title:
        ax.set_title(title, fontsize=12, pad=8)

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# number_line
# ---------------------------------------------------------------------------

def _number_line(spec: dict) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(7, 2.2))

    num_range = spec.get("range", [-5, 5])
    pts       = spec.get("points", [])
    intervals = spec.get("intervals", [])
    title     = spec.get("title", "")

    lo, hi = float(num_range[0]), float(num_range[1])
    pad = (hi - lo) * 0.12

    # Arrow line
    ax.annotate(
        "", xy=(hi + pad, 0), xytext=(lo - pad, 0),
        arrowprops=dict(arrowstyle="-|>", color="black", lw=1.8),
    )

    # Tick marks
    start = int(math.ceil(lo))
    end   = int(math.floor(hi))
    for i in range(start, end + 1):
        ax.plot([i, i], [-0.12, 0.12], "k-", linewidth=1.2)
        ax.text(i, -0.35, str(i), ha="center", va="top", fontsize=9)

    # Shaded intervals
    for iv in intervals:
        s = float(iv.get("start", 0))
        e = float(iv.get("end",   1))
        c = iv.get("color", "#93c5fd")
        ax.fill_betweenx([-0.06, 0.06], s, e, color=c, alpha=0.55, zorder=2)

    # Points
    for pt in pts:
        px   = float(pt.get("x", 0))
        lbl  = pt.get("label", str(px))
        kind = pt.get("type", "closed")
        color = pt.get("color", SECONDARY)
        if kind == "open":
            ax.plot(px, 0, "o", markersize=10, markerfacecolor="white",
                    markeredgecolor=color, markeredgewidth=2.5, zorder=5)
        else:
            ax.plot(px, 0, "o", markersize=10, color=color, zorder=5)
        ax.text(px, 0.35, lbl, ha="center", fontsize=9.5, color=color)

    ax.set_xlim(lo - pad * 1.5, hi + pad * 1.5)
    ax.set_ylim(-0.8, 0.8)
    ax.axis("off")

    if title:
        ax.set_title(title, fontsize=11, pad=6)

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _equal_axes_with_margin(
    ax: plt.Axes,
    points: list[np.ndarray],
    margin: float = 0.5,
) -> None:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ax.set_xlim(min(xs) - margin, max(xs) + margin)
    ax.set_ylim(min(ys) - margin, max(ys) + margin)
