"""
Suite de Auditoría (@AUDITOR) para KineTopus-Pro (Headless Pipeline, Static Renderer y CLI).

Verifica:
  1. Regla de 16GB RAM: contigüidad C y dtype `np.float64` en todos los tensores numéricos.
  2. Contrato completo y serialización JSON pura de `telemetry`.
  3. Doble Sello de Fiabilidad (Ljung-Box + Mini Walk-Forward OOS sin data leakage).
  4. Protección frente a quiebres CUSUM recientes (<15 velas) manteniendo horizonte completo.
  5. Renderizado de `dashboard.png` válido (cabecera PNG binaria) y ejecución E2E del CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kinetopus_pro.headless_pipeline import KinetopusAnalysisConfig, KinetopusHeadlessPipeline
from kinetopus_pro.static_renderer import KinetopusStaticRenderer


@pytest.fixture
def synthetic_inertial_df() -> pd.DataFrame:
    """Serie sintética con ciclos inerciales acoplados Precio-Volumen y 1 cambio de régimen."""
    rng = np.random.default_rng(123)
    n = 650
    dates = pd.date_range("2024-01-01", periods=n, freq="1D")
    t = np.linspace(0, 24 * np.pi, n, dtype=np.float64)

    # Régimen 1 (0..420): oscilación alcista suave; Régimen 2 (420..650): impulso más rápido
    r = np.zeros(n, dtype=np.float64)
    r[:420] = 0.0015 + 0.006 * np.sin(t[:420] * 0.35) + rng.normal(0, 0.003, 420)
    r[420:] = -0.0010 + 0.011 * np.cos(t[420:] * 0.55) + rng.normal(0, 0.004, n - 420)

    close = 100.0 * np.exp(np.cumsum(r))
    volume = 1e6 * (1.0 + 0.35 * np.cos(t * 0.35) + rng.uniform(0.05, 0.25, n))

    return pd.DataFrame({"Close": close, "Volume": volume}, index=dates)


def test_headless_pipeline_memory_and_json_contract(synthetic_inertial_df: pd.DataFrame, tmp_path: Path):
    cfg = KinetopusAnalysisConfig(
        ticker="SYNTH-TEST",
        context_window=500,
        horizon_steps=60,
        wf_cuts=6,
        auto_tune=True,
        auto_rescue=True,
    )
    pipeline = KinetopusHeadlessPipeline(cfg)
    result = pipeline.run(df_override=synthetic_inertial_df)

    # 1. Auditoría de RAM: arrays numéricos float64
    numeric_keys = (
        "t",
        "raw_price",
        "log_returns",
        "r_smooth",
        "r_dot",
        "r_dot2",
        "v_smooth",
        "v_dot",
        "cusum_s_pos",
        "cusum_s_neg",
    )
    for key in numeric_keys:
        arr = result.arrays[key]
        assert isinstance(arr, np.ndarray), f"{key} no es np.ndarray"
        assert arr.dtype == np.float64, f"{key} viola float64 ({arr.dtype})"
        assert arr.flags["C_CONTIGUOUS"], f"{key} no es C-contiguous en RAM"

    # 2. Serialización JSON estricta sin tipos numpy residuales
    serialized = json.dumps(result.telemetry, ensure_ascii=False)
    parsed = json.loads(serialized)

    required_sections = {
        "metadata",
        "calibration",
        "executive_kpis",
        "spectral_layer",
        "white_box_physics",
        "reliability_seal",
        "geometry_and_phase_space",
        "cusum_forensics",
        "forecast_cone",
    }
    assert required_sections.issubset(parsed.keys())

    # 3. Verificar Doble Sello de Fiabilidad
    lb = parsed["reliability_seal"]["ljung_box_whiteness"]
    wf = parsed["reliability_seal"]["mini_walk_forward_oos"]
    assert "verdict" in lb
    assert wf["executed"] is True
    assert wf["total_cuts"] == 6
    assert wf["asset_physics_class"] in {
        "COHERENTE_INERCIAL",
        "TRANSICIONAL_BORDE",
        "EXOGENO_FUNDAMENTALISTA",
        "INESTABLE_O_RUIDO_EXTREMO",
        "INSUFICIENTE",
    }

    # 4. Verificar Geometría, Invalidación CUSUM y Fechas ISO
    assert parsed["cusum_forensics"]["active_regime_end_date"].startswith("2025-")
    inv = parsed["cusum_forensics"]["invalidation_levels_1candle"]
    last_close = parsed["metadata"]["dataset"]["last_close_price"]
    assert inv["downside_regime_break_price"] < last_close < inv["upside_regime_break_price"]

    # 5. Verificar Renderizador PNG Estático
    png_file = tmp_path / "dashboard.png"
    rendered = KinetopusStaticRenderer.render_dashboard(result, str(png_file))
    assert os.path.isfile(rendered)
    with open(rendered, "rb") as f:
        magic = f.read(8)
    assert magic == b"\x89PNG\r\n\x1a\n", "El archivo generado no tiene cabecera PNG válida"
    assert png_file.stat().st_size > 25_000, "El PNG es sospechosamente pequeño"


def test_late_cusum_break_preserves_full_horizon(synthetic_inertial_df: pd.DataFrame):
    """Si ocurre un shock a 5 velas del final (<15 velas), el horizonte proyectado sigue siendo completo."""
    df_shock = synthetic_inertial_df.copy()
    # Inyectar un salto brusco a 5 velas del cierre para forzar un quiebre tardío en CUSUM
    df_shock.iloc[-5:, df_shock.columns.get_loc("Close")] *= 1.35

    cfg = KinetopusAnalysisConfig(
        ticker="SHOCK-TAIL",
        context_window=400,
        horizon_steps=45,
        cusum_k=0.5,
        cusum_h=4.0,
        auto_tune=False,
        wf_cuts=0,
    )
    res = KinetopusHeadlessPipeline(cfg).run(df_override=df_shock)
    det_path = res.arrays["det_price_path"]
    assert len(det_path) == 45, f"Se esperaba horizonte completo de 45 pasos, obtenido {len(det_path)}"


def test_cli_end_to_end_with_local_csv(synthetic_inertial_df: pd.DataFrame, tmp_path: Path):
    csv_path = tmp_path / "sample_asset.csv"
    out_dir = tmp_path / "cli_out"
    df_save = synthetic_inertial_df.reset_index().rename(columns={"index": "Date"})
    df_save.to_csv(csv_path, index=False)

    cli_script = PROJECT_ROOT / "scripts" / "kinetopus_analyze.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(cli_script),
            "--csv",
            str(csv_path),
            "--ticker",
            "CLI-SYNTH",
            "--horizon",
            "30",
            "--wf-cuts",
            "4",
            "--output-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    summary = json.loads(proc.stdout)
    assert summary["status"] == "OK"
    assert summary["ticker"] == "CLI-SYNTH"
    assert Path(summary["telemetry_json"]).is_file()
    assert Path(summary["dashboard_png"]).is_file()
