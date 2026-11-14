"""
Suite de Auditoría Hito 2 (@AUDITOR) — Motor Multi-Lente, Sello Estricto y Refuerzos Visuales.

Verifica:
  1. Paridad numérica exacta entre `_run_fast_cusum_autotune` (FFT en proceso + caché) y `CUSUMAutoTuner.run_search`.
  2. Walk-Forward OOS estricto: ventana completa (`len(p_train) == W`) sin truncamiento y sello `INSUFICIENTE` si `< 5` cortes.
  3. Manejo limpio de `N/D` cuando faltan velas y prohibición de promover la lente media (`1000v`) como fondo.
  4. Jerarquía fija sin votos: si `2000v` reprueba como `EXOGENO_FUNDAMENTALISTA`, el fondo queda `INDETERMINADA (exógena)` y la confianza global se topa en `BAJA_CAUTELA` aunque `1000v` y `500v` aprueben en pleno.
  5. Descarga inteligente única con respaldo automático `10y -> max` (caso ETF/acción de ~252 velas/año vs cripto 365v/año).
  6. Ejecución paralela E2E (`ProcessPoolExecutor` + CLI), contigüidad `np.float64` en `nominal_smooth` y exportación completa de los 22 artefactos PNG (`confluence.png` + 3 `dashboard.png` + 18 `panels/*.png`).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kinetopus_pro.engine_bridge import CUSUMAutoTuner, MarketLoader
from kinetopus_pro.headless_pipeline import KinetopusAnalysisConfig, KinetopusHeadlessPipeline
from kinetopus_pro.multi_lens import KinetopusMultiLensRunner, MultiLensConfig


def _build_synthetic_df(n: int, seed: int = 2026) -> pd.DataFrame:
    """Construye una serie sintética acoplada Precio-Volumen con ciclos inerciales suaves."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=n, freq="1D")
    t = np.linspace(0.0, (n / 25.0) * np.pi, n, dtype=np.float64)

    split = int(n * 0.65)
    r = np.zeros(n, dtype=np.float64)
    r[:split] = 0.0012 + 0.0055 * np.sin(t[:split] * 0.40) + rng.normal(0.0, 0.0025, split)
    r[split:] = 0.0008 + 0.0075 * np.cos(t[split:] * 0.30) + rng.normal(0.0, 0.0028, n - split)

    close = 100.0 * np.exp(np.cumsum(r))
    volume = 1e6 * (1.0 + 0.30 * np.cos(t * 0.40) + rng.uniform(0.05, 0.25, n))
    return pd.DataFrame({"Close": close, "Volume": volume}, index=dates)


def test_fast_cusum_autotune_exact_parity_with_upstream():
    """Garantiza que la calibración rápida en proceso da el mismo k* y fitness que CUSUMAutoTuner."""
    df_sample = _build_synthetic_df(320, seed=77)

    upstream_tuner = CUSUMAutoTuner(df_sample.copy(), disable_norm=False, disable_returns=False)
    k_up, rep_up = upstream_tuner.run_search(min_drift=0.2, max_drift=3.0, steps=0.2)

    cfg = KinetopusAnalysisConfig(ticker="PARITY", in_process_fft=True)
    fast_pipe = KinetopusHeadlessPipeline(cfg)
    k_fast, rep_fast = fast_pipe._run_fast_cusum_autotune(
        df_sample.copy(), min_drift=0.2, max_drift=3.0, steps=0.2
    )

    assert k_fast == k_up
    assert rep_fast["num_quiebres"] == rep_up["num_quiebres"]
    assert abs(rep_fast["fitness"] - rep_up["fitness"]) < 1e-11
    assert abs(rep_fast["weighted_r2"] - rep_up["weighted_r2"]) < 1e-11


def test_strict_walk_forward_full_window_and_insuficiente_seal():
    """Verifica que nunca se trunca `p_train` y que <5 cortes efectivos producen sello `INSUFICIENTE`."""
    # Caso A: Margen suficiente para >= 5 cortes de ventana completa (W=400, n=620, eval_h=30)
    df_ok = _build_synthetic_df(620, seed=101)
    cfg_ok = KinetopusAnalysisConfig(
        ticker="WF-FULL",
        context_window=400,
        horizon_steps=30,
        wf_cuts=8,
        min_wf_effective_cuts=5,
        strict_wf_window=True,
        auto_tune=False,
        auto_rescue=False,
        cusum_k=1.2,
    )
    res_ok = KinetopusHeadlessPipeline(cfg_ok).run(df_override=df_ok)
    wf_ok = res_ok.telemetry["reliability_seal"]["mini_walk_forward_oos"]
    assert wf_ok["strict_full_window_enforced"] is True
    assert wf_ok["effective_cuts"] >= 5
    assert wf_ok["min_train_candles_used"] == 400
    assert wf_ok["max_train_candles_used"] == 400

    # Caso B: Historial apenas mayor que W + eval_h (n=435, W=400, eval_h=30 -> solo caben <=2 cortes < 5)
    df_short = df_ok.iloc[-435:].copy()
    cfg_short = KinetopusAnalysisConfig(
        ticker="WF-INSUF",
        context_window=400,
        horizon_steps=30,
        wf_cuts=8,
        min_wf_effective_cuts=5,
        strict_wf_window=True,
        auto_tune=False,
        auto_rescue=False,
        cusum_k=1.2,
    )
    res_short = KinetopusHeadlessPipeline(cfg_short).run(df_override=df_short)
    wf_short = res_short.telemetry["reliability_seal"]["mini_walk_forward_oos"]
    seal_short = res_short.telemetry["reliability_seal"]["double_seal_summary"]

    assert wf_short["effective_cuts"] < 5
    assert wf_short["asset_physics_class"] == "INSUFICIENTE"
    assert wf_short["seal_approved"] is False
    assert seal_short["seal_passed"] is False
    assert seal_short["seal_grade"] == "INSUFICIENTE"


def test_nd_graceful_handling_and_no_hierarchy_promotion():
    """Si un activo solo tiene 1,250 velas, 2000v es `N/D`, 1000v NO la reemplaza y la confianza se topa."""
    df_mid = _build_synthetic_df(1250, seed=303)
    m_cfg = MultiLensConfig(
        ticker="ND-ASSET",
        lenses=(2000, 1000, 500),
        horizon_steps=30,
        wf_cuts=6,
        min_wf_effective_cuts=5,
        auto_tune=False,
        auto_rescue=False,
        cusum_k=1.2,
        parallel=False,
    )
    multi_res = KinetopusMultiLensRunner(m_cfg).run(df_override=df_mid)
    conf = multi_res.confluence
    hier = conf["hierarchy_verdict"]
    lenses_sum = conf["lenses_summary"]

    assert lenses_sum["2000"]["status"] == "N/D"
    assert lenses_sum["2000"]["available"] is False
    assert lenses_sum["1000"]["status"] == "OK"
    assert lenses_sum["500"]["status"] == "OK"

    assert hier["background_trend_2000v"].startswith("N/D")
    assert hier["alignment_pattern"] == "FONDO_INDETERMINADO_POR_SELLO_LARGO"
    assert hier["global_physical_confidence"] in {"BAJA_CAUTELA", "NULA_O_DEGRADADA"}


def test_fixed_hierarchy_2000v_exogenous_caps_global_confidence():
    """Aunque 1000v y 500v tengan APROBADO_PLENO, si 2000v reprueba como exógena el tope es BAJA_CAUTELA."""
    mock_failed_macro = [
        {
            "window_candles": 2000,
            "available": True,
            "seal_passed": False,
            "seal_grade": "REPROBADO_EXOGENO",
            "oos_physics_class": "EXOGENO_FUNDAMENTALISTA",
            "oos_consensus_hr_pct": 44.0,
            "oos_effective_cuts": 10,
            "sindy_r2_score": 0.72,
            "raw_direction": "ALCISTA",
            "quadrant": "Q1_IMPULSO_ALCISTA_ACELERANDO",
            "lens_confidence": "BAJA_CAUTELA",
        },
        {
            "window_candles": 1000,
            "available": True,
            "seal_passed": True,
            "seal_grade": "APROBADO_PLENO",
            "oos_physics_class": "COHERENTE_INERCIAL",
            "oos_consensus_hr_pct": 65.0,
            "oos_effective_cuts": 10,
            "sindy_r2_score": 0.85,
            "raw_direction": "ALCISTA",
            "quadrant": "Q1_IMPULSO_ALCISTA_ACELERANDO",
            "lens_confidence": "ALTA",
        },
        {
            "window_candles": 500,
            "available": True,
            "seal_passed": True,
            "seal_grade": "APROBADO_PLENO",
            "oos_physics_class": "COHERENTE_INERCIAL",
            "oos_consensus_hr_pct": 70.0,
            "oos_effective_cuts": 10,
            "sindy_r2_score": 0.88,
            "raw_direction": "ALCISTA",
            "quadrant": "Q1_IMPULSO_ALCISTA_ACELERANDO",
            "lens_confidence": "ALTA",
        },
    ]
    verdict_capped = KinetopusMultiLensRunner._synthesize_fixed_hierarchy(mock_failed_macro)
    assert verdict_capped["background_trend_2000v"] == "INDETERMINADA (exógena)"
    assert verdict_capped["medium_confirmation_1000v"].startswith("ACTIVA_AISLADA_ALCISTA")
    assert verdict_capped["alignment_pattern"] == "FONDO_INDETERMINADO_POR_SELLO_LARGO"
    assert verdict_capped["global_physical_confidence"] == "BAJA_CAUTELA"

    # Camino feliz: las 3 lentes aprueban en pleno en la misma dirección
    mock_all_ok = [dict(item) for item in mock_failed_macro]
    mock_all_ok[0].update(
        {
            "seal_passed": True,
            "seal_grade": "APROBADO_PLENO",
            "oos_physics_class": "COHERENTE_INERCIAL",
            "oos_consensus_hr_pct": 62.0,
            "lens_confidence": "ALTA",
        }
    )
    verdict_full = KinetopusMultiLensRunner._synthesize_fixed_hierarchy(mock_all_ok)
    assert verdict_full["background_trend_2000v"] == "ALCISTA (APROBADO_PLENO)"
    assert verdict_full["medium_confirmation_1000v"] == "CONFIRMADA_ALCISTA"
    assert verdict_full["alignment_pattern"] == "ALINEACION_JERARQUICA_PLENA_ALCISTA"
    assert verdict_full["global_physical_confidence"] == "ALTA"


def test_smart_download_10y_to_max_fallback(monkeypatch: pytest.MonkeyPatch):
    """Simula un ETF bursátil (~2515 velas en 10y < 2690 óptimas) vs un cripto (~3653 velas en 10y)."""
    calls: List[str] = []
    df_2515 = _build_synthetic_df(2515, seed=11)
    df_4200 = _build_synthetic_df(4200, seed=12)

    def _fake_etf_loader(ticker: str, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
        calls.append(period)
        return df_2515 if period == "10y" else df_4200

    monkeypatch.setattr(MarketLoader, "load_ticker_data", staticmethod(_fake_etf_loader))
    runner_etf = KinetopusMultiLensRunner(MultiLensConfig(ticker="SPY-MOCK"))
    df_res, meta_etf = runner_etf._load_smart_dataset()

    assert calls == ["10y", "max"]
    assert meta_etf["fallback_to_max_triggered"] is True
    assert meta_etf["effective_period_used"] == "max"
    assert len(df_res) == 4200

    # Cripto 24/7 con 3,653 velas en 10y: NO debe disparar segunda descarga
    calls_crypto: List[str] = []
    df_3653 = _build_synthetic_df(3653, seed=13)

    def _fake_crypto_loader(ticker: str, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
        calls_crypto.append(period)
        return df_3653

    monkeypatch.setattr(MarketLoader, "load_ticker_data", staticmethod(_fake_crypto_loader))
    runner_crypto = KinetopusMultiLensRunner(MultiLensConfig(ticker="BTC-MOCK"))
    df_res_c, meta_crypto = runner_crypto._load_smart_dataset()

    assert calls_crypto == ["10y"]
    assert meta_crypto["fallback_to_max_triggered"] is False
    assert meta_crypto["effective_period_used"] == "10y"
    assert len(df_res_c) == 3653


def test_multi_lens_parallel_cli_and_all_visual_artifacts(tmp_path: Path):
    """Audita contigüidad float64 en paralelo y los 22 PNG generados por el CLI Multi-Lente."""
    df_full = _build_synthetic_df(1100, seed=505)

    # 1. Auditoría en memoria con ProcessPoolExecutor activo
    m_cfg = MultiLensConfig(
        ticker="PARALLEL-MEM",
        lenses=(700, 500, 300),
        horizon_steps=35,
        wf_cuts=5,
        min_wf_effective_cuts=5,
        auto_tune=False,
        auto_rescue=False,
        cusum_k=1.1,
        parallel=True,
    )
    m_res = KinetopusMultiLensRunner(m_cfg).run(df_override=df_full)
    assert len(m_res.lens_slots) == 3
    for slot in m_res.lens_slots:
        assert slot.available is True
        assert slot.run_result is not None
        nom = slot.run_result.arrays["nominal_smooth"]
        assert isinstance(nom, np.ndarray)
        assert nom.dtype == np.float64
        assert nom.flags["C_CONTIGUOUS"]
        assert len(nom) == slot.window_candles
        kin = slot.run_result.telemetry["geometry_and_phase_space"]["kinematics"]
        assert "price_vs_spline_gap_pct" in kin
        assert "rotation_sense" in slot.run_result.telemetry["geometry_and_phase_space"]["phase_space"]

    # 2. Ejecución E2E del CLI exportando `confluence.png` + 3 `dashboard.png` + 18 `panels/*.png`
    csv_path = tmp_path / "multi_asset.csv"
    out_dir = tmp_path / "multi_report"
    df_full.reset_index().rename(columns={"index": "Date"}).to_csv(csv_path, index=False)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "kinetopus_pro.cli",
            "--csv",
            str(csv_path),
            "--ticker",
            "MULTI-CLI",
            "--lenses",
            "700,500,300",
            "--horizon",
            "35",
            "--wf-cuts",
            "5",
            "--no-auto-tune",
            "--no-auto-rescue",
            "--cusum-k",
            "1.1",
            "--output-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    summary = json.loads(proc.stdout)
    assert summary["status"] == "OK"
    assert summary["mode"] == "multi_lens"

    conf_png = Path(summary["confluence_png"])
    conf_json = Path(summary["confluence_json"])
    assert conf_json.is_file()
    assert conf_png.is_file()

    png_files: List[Path] = [conf_png]
    for w in ("700", "500", "300"):
        l_meta = summary["lenses"][w]
        assert l_meta["status"] == "OK"
        assert Path(l_meta["telemetry_json"]).is_file()
        d_png = Path(l_meta["dashboard_png"])
        assert d_png.is_file()
        png_files.append(d_png)

        panels_map = l_meta["individual_panels"]
        assert len(panels_map) == 6
        for p_path_str in panels_map.values():
            p_path = Path(p_path_str)
            assert p_path.is_file()
            png_files.append(p_path)

    assert len(png_files) == 22
    for png_f in png_files:
        with open(png_f, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n", f"Cabecera PNG inválida en {png_f}"
        assert png_f.stat().st_size > 15_000, f"PNG demasiado pequeño: {png_f}"
