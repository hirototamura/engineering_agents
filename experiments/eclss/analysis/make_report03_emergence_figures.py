#!/usr/bin/env python3
"""Draw the ver.03 emergence figures from docs/data CSVs and report03_emergence.json."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "docs" / "data"
FIG = REPO / "docs" / "images" / "results"
_EMERGENCE_CANDIDATES = (
    DATA / "report03_emergence.json",
    REPO / "experiments" / "outputs" / "report03_emergence.json",
)
EMERGENCE = next(path for path in _EMERGENCE_CANDIDATES if path.is_file())

PHASE_KEYS = ("phase1", "phase2", "phase3", "phase4")
PHASE_LABELS = ("① 記憶なし", "② 記憶", "③ 記憶+採点", "④ 監査パネル")
PHASE_COLORS = ("#9ecae1", "#2171b5", "#08306b", "#d94801")

INTENT_ORDER = (
    "wrs_trim",
    "wrs_restore",
    "floor_lock",
    "below_floor_avoid",
    "hold_current",
    "other",
)
INTENT_LABELS = {
    "wrs_trim": "WRS を削る",
    "wrs_restore": "WRS を戻す",
    "floor_lock": "ガス下限を守る",
    "below_floor_avoid": "下限割れ回避",
    "hold_current": "現状維持",
    "other": "その他",
}
INTENT_COLORS = {
    "wrs_trim": "#2171b5",
    "wrs_restore": "#6baed6",
    "floor_lock": "#08306b",
    "below_floor_avoid": "#d94801",
    "hold_current": "#969696",
    "other": "#d9d9d9",
}

plt.rcParams.update(
    {
        "font.family": ["Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans CJK JP", "DejaVu Sans"],
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def load_emergence() -> dict:
    return json.loads(EMERGENCE.read_text(encoding="utf-8"))


def load_phase_csv(prefix: str) -> list[dict]:
    path = DATA / f"{prefix}_iteration_metrics.csv"
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _f(row: dict, key: str) -> float:
    value = row.get(key, "")
    if value in (None, ""):
        return float("nan")
    return float(value)


def draw_reasoning_intent(emergence: dict) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    x = np.arange(len(PHASE_KEYS))
    bottoms = np.zeros(len(PHASE_KEYS))
    for intent in INTENT_ORDER:
        heights = [
            float(emergence[phase]["intent_counts"].get(intent, 0)) for phase in PHASE_KEYS
        ]
        ax.bar(
            x,
            heights,
            bottom=bottoms,
            color=INTENT_COLORS[intent],
            width=0.62,
            label=INTENT_LABELS[intent],
        )
        bottoms += np.array(heights)
    ax.set_xticks(x, PHASE_LABELS)
    ax.set_ylabel("周数（設計者 reasoning の意図クラス）")
    ax.set_title("言ったこと — 設計者本文から分類した意図")
    ax.set_ylim(0, 55)
    ax.legend(loc="upper right", frameon=False, ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "report03_reasoning_intent.svg")
    plt.close(fig)


def draw_said_vs_did(emergence: dict) -> None:
    rates = [100.0 * emergence[phase]["said_vs_did"]["rate"] for phase in PHASE_KEYS]
    agrees = [emergence[phase]["said_vs_did"]["agree"] for phase in PHASE_KEYS]
    ns = [emergence[phase]["said_vs_did"]["n"] for phase in PHASE_KEYS]
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    bars = ax.bar(PHASE_LABELS, rates, color=PHASE_COLORS, width=0.58)
    ax.set_ylabel("意図クラスと設置差分クラスの一致率 (%)")
    ax.set_title("言ったことと置いた機体 — 一致率")
    ax.set_ylim(0, 55)
    for bar, agree, n, rate in zip(bars, agrees, ns, rates):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.2,
            f"{agree}/{n}\n{rate:.0f}%",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(FIG / "report03_said_vs_did.svg")
    plt.close(fig)


def draw_audit_votes(emergence: dict) -> None:
    votes = emergence["phase4"]["audit_decisions"]
    lenses = ("rederive_numbers", "avoid_local_optima", "design_validity")
    lens_labels = ("数値の再導出", "局所最適の回避", "設計の妥当性")
    outcomes = ("approve", "reject", "fallback")
    outcome_colors = {"approve": "#2ca02c", "reject": "#d62728", "fallback": "#7f7f7f"}
    outcome_labels = {"approve": "approve", "reject": "reject", "fallback": "fallback"}
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    x = np.arange(len(lenses))
    width = 0.26
    for i, outcome in enumerate(outcomes):
        heights = [float(votes.get(f"{lens}:{outcome}", 0)) for lens in lenses]
        ax.bar(
            x + (i - 1) * width,
            heights,
            width=width,
            color=outcome_colors[outcome],
            label=outcome_labels[outcome],
        )
    ax.set_xticks(x, lens_labels)
    ax.set_ylabel("票数（50 周 × 3 監査）")
    ax.set_title("段階④ 監査パネルの票 — 局所最適回避が 44 回 reject")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(FIG / "report03_audit_votes.svg")
    plt.close(fig)


def draw_rho_tracks() -> None:
    fig, axes = plt.subplots(1, 3, figsize=(8.6, 3.15), sharex=True)
    series = (
        ("theory_ars_coverage", "ρ_ARS（対 理論下限 20.8）", 1.0),
        ("theory_ogs_coverage", "ρ_OGS（対 理論下限 42.0）", 1.0),
        ("theory_wrs_coverage", "ρ_WRS（対 需要換算）", 1.0),
    )
    for ax, (key, title, floor) in zip(axes, series):
        for prefix, label, color in zip(PHASE_KEYS, PHASE_LABELS, PHASE_COLORS):
            rows = load_phase_csv(prefix)
            xs = [_f(row, "iteration") for row in rows]
            ys = [_f(row, key) for row in rows]
            ax.plot(xs, ys, color=color, lw=1.4, label=label)
        ax.axhline(floor, color="#444444", ls="--", lw=0.8)
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("iteration")
        ax.set_xlim(1, 50)
    axes[0].set_ylabel("カバレッジ比")
    axes[0].legend(frameon=False, fontsize=7, loc="upper right")
    fig.suptitle("4 連鎖のカバレッジ軌跡 — ガスは下限へ、水だけが動く", y=1.02, fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "report03_rho_tracks.svg", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    emergence = load_emergence()
    draw_reasoning_intent(emergence)
    draw_said_vs_did(emergence)
    draw_audit_votes(emergence)
    draw_rho_tracks()
    print("wrote", FIG / "report03_reasoning_intent.svg")
    print("wrote", FIG / "report03_said_vs_did.svg")
    print("wrote", FIG / "report03_audit_votes.svg")
    print("wrote", FIG / "report03_rho_tracks.svg")


if __name__ == "__main__":
    main()
