import csv
from pathlib import Path


OUT = Path("outputs")
SERIES = [
    ("段階① 初期", "phase1", "#9ecae1"),
    ("段階② 記憶あり改善", "phase2", "#2171b5"),
    ("段階③ 記憶+評価変更", "phase3", "#08306b"),
    ("段階④ 監査パネル", "phase4", "#d94801"),
]
PARAMS = [
    ("ARS capacity kg/day", "config_ars", 0, 32, 20.8, "theory floor 20.8"),
    ("OGS capacity kg/day", "config_ogs", 0, 58, 42.0, "theory floor 42.0"),
    ("WRS max feed L/op", "config_wrs", 0, 10.5, None, None),
]


def read_rows(prefix):
    with (OUT / f"{prefix}_iteration_metrics.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [
        {
            "iteration": int(row["iteration"]),
            "config_ars": float(row["config_ars"]),
            "config_ogs": float(row["config_ogs"]),
            "config_wrs": float(row["config_wrs"]),
        }
        for row in rows
    ]


def scale(v, lo, hi, a, b):
    if hi == lo:
        return (a + b) / 2
    return a + (v - lo) * (b - a) / (hi - lo)


def points(rows, key, xmin, xmax, x0, x1, ymin, ymax, y0, y1):
    return " ".join(
        f"{scale(row['iteration'], xmin, xmax, x0, x1):.1f},{scale(row[key], ymin, ymax, y0, y1):.1f}"
        for row in rows
    )


data = [(label, read_rows(prefix), color) for label, prefix, color in SERIES]
w, h = 1260, 900
left, right, top, bottom = 84, 230, 58, 68
plot_gap = 60
plot_h = (h - top - bottom - plot_gap * 2) / 3
x0, x1 = left, w - right
xmin, xmax = 1, max(row["iteration"] for _, rows, _ in data for row in rows)

elems = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
    '<rect width="100%" height="100%" fill="white"/>',
    f'<text x="{w/2}" y="32" font-size="22" text-anchor="middle" font-family="Arial">段階①-④の3パラメータ推移</text>',
]

for idx, (title, key, ymin, ymax, ref, ref_label) in enumerate(PARAMS):
    y_top = top + idx * (plot_h + plot_gap)
    y_bottom = y_top + plot_h
    elems.append(f'<text x="{x0}" y="{y_top-14:.1f}" font-size="15" font-family="Arial">{title}</text>')
    elems.append(f'<rect x="{x0}" y="{y_top:.1f}" width="{x1-x0}" height="{plot_h:.1f}" fill="none" stroke="#333"/>')
    for t in range(6):
        val = ymin + (ymax - ymin) * t / 5
        y = scale(val, ymin, ymax, y_bottom, y_top)
        elems.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#e6e6e6"/>')
        elems.append(f'<text x="{x0-10}" y="{y+5:.1f}" font-size="12" text-anchor="end" font-family="Arial">{val:.1f}</text>')
    if ref is not None:
        y = scale(ref, ymin, ymax, y_bottom, y_top)
        elems.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#777" stroke-dasharray="6 5"/>')
        elems.append(f'<text x="{x1-8}" y="{y-6:.1f}" font-size="12" text-anchor="end" font-family="Arial" fill="#555">{ref_label}</text>')
    for tick in range(xmin, xmax + 1, 5):
        x = scale(tick, xmin, xmax, x0, x1)
        elems.append(f'<line x1="{x:.1f}" y1="{y_bottom:.1f}" x2="{x:.1f}" y2="{y_bottom+5:.1f}" stroke="#333"/>')
        if idx == 2:
            elems.append(f'<text x="{x:.1f}" y="{y_bottom+22:.1f}" font-size="11" text-anchor="middle" font-family="Arial">{tick}</text>')
    for label, rows, color in data:
        elems.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{points(rows, key, xmin, xmax, x0, x1, ymin, ymax, y_bottom, y_top)}"/>'
        )
        for row in [rows[0], rows[-1]]:
            x = scale(row["iteration"], xmin, xmax, x0, x1)
            y = scale(row[key], ymin, ymax, y_bottom, y_top)
            elems.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"><title>{label} iteration {row["iteration"]}: {row[key]:.4g}</title></circle>')

legend_x = x1 + 24
legend_y = top + 28
for label, _, color in data:
    elems.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x+44}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>')
    elems.append(f'<text x="{legend_x+54}" y="{legend_y+5}" font-size="13" font-family="Arial">{label}</text>')
    legend_y += 32
elems.append(f'<text x="{(x0+x1)/2}" y="{h-18}" font-size="15" text-anchor="middle" font-family="Arial">Iteration</text>')
elems.append("</svg>")

(OUT / "ssos_phase1_phase2_phase3_parameter_trends.svg").write_text("\n".join(elems), encoding="utf-8")
