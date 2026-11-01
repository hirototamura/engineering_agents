import argparse
import csv
from pathlib import Path


def read_float(row, key):
    val = row.get(key, "")
    return 0.0 if val in {"", None} else float(val)


def scale(v, lo, hi, a, b):
    if hi == lo:
        return (a + b) / 2
    return a + (v - lo) * (b - a) / (hi - lo)


parser = argparse.ArgumentParser()
parser.add_argument("--prefix", required=True)
parser.add_argument("--title", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()

out = Path("outputs")
rows = list(csv.DictReader((out / f"{args.prefix}_iteration_metrics.csv").open(encoding="utf-8")))

components = [
    ("A Survival", "A", "#2d6a4f", lambda r: read_float(r, "axis_actor_survival")),
    (
        "B-D System",
        "B-D",
        "#277da1",
        lambda r: read_float(r, "axis_tcl")
        + read_float(r, "axis_environment_trajectory")
        + read_float(r, "axis_resource_recovery"),
    ),
    ("E-F Footprint", "E-F", "#f3722c", lambda r: read_float(r, "axis_cost") + read_float(r, "axis_mass")),
    (
        "G Ops/Physics",
        "G",
        "#9d4edd",
        lambda r: read_float(r, "axis_actor_decision") + read_float(r, "axis_physical_response"),
    ),
]

with (out / f"{args.output}.csv").open("w", encoding="utf-8", newline="") as fh:
    writer = csv.writer(fh)
    writer.writerow(["iteration", "score", "A_survival", "B_D_system", "E_F_footprint", "G_ops_physics"])
    for row in rows:
        writer.writerow([row["iteration"], row["score"], *[round(fn(row), 6) for _, _, _, fn in components]])

w, h = 1260, 640
left, right, top, bottom = 84, 230, 62, 82
x0, x1 = left, w - right
y0, y1 = h - bottom, top
iters = [int(row["iteration"]) for row in rows]
xmin, xmax = min(iters), max(iters)
bar_gap = 5 if len(rows) > 25 else 10
bar_w = max(7, ((x1 - x0) / len(rows)) - bar_gap)

elems = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
    '<rect width="100%" height="100%" fill="white"/>',
    f'<text x="{w/2}" y="34" font-size="22" text-anchor="middle" font-family="Arial">{args.title}</text>',
    f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#333"/>',
    f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="#333"/>',
]

for tick in range(0, 101, 10):
    y = scale(tick, 0, 100, y0, y1)
    elems.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#e7e7e7"/>')
    elems.append(f'<text x="{x0-10}" y="{y+5:.1f}" font-size="12" text-anchor="end" font-family="Arial">{tick}</text>')

label_step = 1 if len(rows) <= 15 else 5
for row in rows:
    iteration = int(row["iteration"])
    center = scale(iteration, xmin, xmax, x0 + bar_w / 2, x1 - bar_w / 2)
    x = center - bar_w / 2
    baseline = 0.0
    for label, short, color, fn in components:
        val = fn(row)
        y_top = scale(baseline + val, 0, 100, y0, y1)
        y_bottom = scale(baseline, 0, 100, y0, y1)
        height = y_bottom - y_top
        if height > 0:
            elems.append(
                f'<rect x="{x:.1f}" y="{y_top:.1f}" width="{bar_w:.1f}" height="{height:.1f}" fill="{color}">'
                f'<title>Iteration {iteration}: {label} {val:.2f} points</title></rect>'
            )
            if height >= 20 and bar_w >= 20:
                elems.append(
                    f'<text x="{center:.1f}" y="{y_top + height / 2 + 4:.1f}" font-size="10" text-anchor="middle" font-family="Arial" fill="white">{short}</text>'
                )
        baseline += val
    if iteration == 1 or iteration == xmax or iteration % label_step == 0:
        elems.append(f'<text x="{center:.1f}" y="{y0+23}" font-size="12" text-anchor="middle" font-family="Arial">{iteration}</text>')

for row in rows:
    iteration = int(row["iteration"])
    if iteration in {1, xmax} or iteration % 10 == 0:
        center = scale(iteration, xmin, xmax, x0 + bar_w / 2, x1 - bar_w / 2)
        score_y = scale(float(row["score"]), 0, 100, y0, y1)
        elems.append(f'<text x="{center:.1f}" y="{score_y-6:.1f}" font-size="10" text-anchor="middle" font-family="Arial">{float(row["score"]):.1f}</text>')

elems.append(f'<text x="{(x0+x1)/2}" y="{h-20}" font-size="15" text-anchor="middle" font-family="Arial">Iteration</text>')
elems.append(f'<text x="24" y="{(y0+y1)/2}" font-size="15" text-anchor="middle" transform="rotate(-90,24,{(y0+y1)/2})" font-family="Arial">Score contribution / 100</text>')

legend_x = x1 + 24
legend_y = top + 24
for label, short, color, _ in components:
    elems.append(f'<rect x="{legend_x}" y="{legend_y-12}" width="14" height="14" fill="{color}"/>')
    elems.append(f'<text x="{legend_x+22}" y="{legend_y}" font-size="13" font-family="Arial">{short}: {label.split(" ", 1)[1]}</text>')
    legend_y += 28
elems.append(f'<text x="{legend_x}" y="{legend_y+10}" font-size="12" font-family="Arial" fill="#555">B-D = TCL + environment + recovery</text>')
elems.append(f'<text x="{legend_x}" y="{legend_y+30}" font-size="12" font-family="Arial" fill="#555">E-F = cost + mass</text>')
elems.append("</svg>")

(out / f"{args.output}.svg").write_text("\n".join(elems), encoding="utf-8")
