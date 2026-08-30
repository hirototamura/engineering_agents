import csv
from pathlib import Path


OUT = Path("outputs")
SERIES = [
    ("段階① 初期", "phase1", "#9ecae1"),
    ("段階② 記憶あり改善", "phase2", "#2171b5"),
    ("段階③ 記憶+評価変更", "phase3", "#08306b"),
]


def read_rows(prefix):
    with (OUT / f"{prefix}_iteration_metrics.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [
        {
            "iteration": int(row["iteration"]),
            "crew": float(row["crew_remaining"]),
            "score": float(row["score"]),
        }
        for row in rows
    ]


def scale(v, lo, hi, a, b):
    if hi == lo:
        return (a + b) / 2
    return a + (v - lo) * (b - a) / (hi - lo)


def path_for(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


data = [(label, read_rows(prefix), color) for label, prefix, color in SERIES]
w, h = 1260, 760
left, right, top, bottom = 78, 180, 58, 72
gap = 70
plot_h = (h - top - bottom - gap) / 2
score_values = [row["score"] for _, rows, _ in data for row in rows]
score_min = max(0, int(min(score_values) // 10 * 10))
score_max = min(100, int((max(score_values) + 9) // 10 * 10))
plots = [
    ("Crew remaining / 50", "crew", 0, 50, top),
    ("Evaluation score / 100", "score", score_min, score_max, top + plot_h + gap),
]
x0, x1 = left, w - right
xmin, xmax = 1, max(row["iteration"] for _, rows, _ in data for row in rows)

elems = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
    '<rect width="100%" height="100%" fill="white"/>',
    f'<text x="{w/2}" y="32" font-size="22" text-anchor="middle" font-family="Arial">段階①-③の生存者数・スコア推移</text>',
]

for title, key, ymin, ymax, ytop in plots:
    y1 = ytop
    y0 = ytop + plot_h
    elems.append(f'<text x="{x0}" y="{y1-14:.1f}" font-size="15" font-family="Arial">{title}</text>')
    elems.append(f'<rect x="{x0}" y="{y1:.1f}" width="{x1-x0}" height="{plot_h:.1f}" fill="none" stroke="#333"/>')
    tick_count = 5
    for t in range(tick_count + 1):
        val = ymin + (ymax - ymin) * t / tick_count
        y = scale(val, ymin, ymax, y0, y1)
        elems.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#e6e6e6"/>')
        elems.append(f'<text x="{x0-10}" y="{y+5:.1f}" font-size="12" text-anchor="end" font-family="Arial">{val:.0f}</text>')
    for tick in range(xmin, xmax + 1, 5):
        x = scale(tick, xmin, xmax, x0, x1)
        elems.append(f'<line x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y0+5:.1f}" stroke="#333"/>')
        elems.append(f'<text x="{x:.1f}" y="{y0+22:.1f}" font-size="11" text-anchor="middle" font-family="Arial">{tick}</text>')
    for label, rows, color in data:
        pts = [
            (scale(row["iteration"], xmin, xmax, x0, x1), scale(row[key], ymin, ymax, y0, y1))
            for row in rows
        ]
        elems.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.7" points="{path_for(pts)}"/>')
        for row in [rows[0], rows[-1], max(rows, key=lambda r: r[key])]:
            x = scale(row["iteration"], xmin, xmax, x0, x1)
            y = scale(row[key], ymin, ymax, y0, y1)
            elems.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"><title>{label} iteration {row["iteration"]}: {row[key]:.2f}</title></circle>')

legend_x = x1 + 24
legend_y = top + 26
for label, _, color in data:
    elems.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x+44}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>')
    elems.append(f'<text x="{legend_x+54}" y="{legend_y+5}" font-size="14" font-family="Arial">{label}</text>')
    legend_y += 28

elems.append(f'<text x="{(x0+x1)/2}" y="{h-18}" font-size="15" text-anchor="middle" font-family="Arial">Iteration</text>')
elems.append("</svg>")

(OUT / "ssos_phase1_phase2_phase3_survival_score_trend.svg").write_text("\n".join(elems), encoding="utf-8")
