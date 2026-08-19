"""Tests for the offline plant_sim ops cheatsheet."""

from __future__ import annotations

import pytest

from tools.plant_sim_ops_cheatsheet import CheatsheetRow, plot_cheatsheet, sweep


def test_cheatsheet_none_metabolism_scales_with_n():
    rows = sweep(n_max=3, steps=5)
    none_rows = {row.n: row for row in rows if row.mode == "none"}
    one = none_rows[1].per_step()
    three = none_rows[3].per_step()
    assert three.o2_metabolism_kg == pytest.approx(3 * one.o2_metabolism_kg, rel=1e-6)
    assert three.co2_metabolism_kg == pytest.approx(3 * one.co2_metabolism_kg, rel=1e-6)
    assert three.co2_ops_kg == 0.0
    assert three.o2_ops_kg == 0.0


def test_cheatsheet_ars_reduces_cabin_co2_vs_none():
    rows = sweep(n_max=2, steps=8)
    none_n2 = next(row for row in rows if row.n == 2 and row.mode == "none")
    ars_n2 = next(row for row in rows if row.n == 2 and row.mode == "ars")
    assert ars_n2.co2_ops_kg > 0.0
    assert ars_n2.co2_net_kg < none_n2.co2_net_kg


def test_cheatsheet_ogs_adds_o2_and_uses_water():
    rows = sweep(n_max=1, steps=8)
    none_row = next(row for row in rows if row.mode == "none")
    ogs_row = next(row for row in rows if row.mode == "ogs")
    assert ogs_row.o2_ops_kg > 0.0
    assert ogs_row.o2_net_kg > none_row.o2_net_kg
    assert ogs_row.water_ops_l > 0.0


def test_cheatsheet_plot_writes_png(tmp_path):
    rows = [
        CheatsheetRow(
            n=1,
            mode="none",
            steps=4,
            metabolism_steps=3,
            co2_metabolism_kg=0.1,
            co2_ops_kg=0.0,
            co2_net_kg=0.1,
            o2_metabolism_kg=0.05,
            o2_ops_kg=0.0,
            o2_net_kg=-0.05,
            water_metabolism_l=0.2,
            water_ops_l=0.0,
            water_net_l=-0.2,
        )
    ]
    png = tmp_path / "ops_cheatsheet.png"
    plot_cheatsheet(rows, png)
    assert png.exists()
    assert png.stat().st_size > 0
