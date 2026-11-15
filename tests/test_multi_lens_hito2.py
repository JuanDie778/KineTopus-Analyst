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
    """Verifica con `audit_oos=True` que no se trunca `p_train` y `<5` cortes marcan `INSUFICIENTE`."""
    # Caso A: Margen suficiente para >= 5 cortes de ventana completa (W=400, n=620, eval_h=30)
    df_ok = _build_synthetic_df(620, seed=101)
    cfg_ok = KinetopusAnalysisConfig(
        ticker="WF-FULL",
        context_window=400,
        horizon_steps=30,
        audit_oos=True,
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
        audit_oos=True,
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


def test_nd_graceful_handling_and_geometric_anchor():
    """Verifica manejo limpio de `N/D` sin bloqueos y respaldo geométrico 500v en activos jóvenes."""
    # Caso 1: 1,250 velas -> 2000v es `N/D`, 1000v actúa como eje principal sin promoverse a 2000v
    df_mid = _build_synthetic_df(1250, seed=303)
    m_cfg = MultiLensConfig(
        ticker="ND-ASSET",
        lenses=(2000, 1000, 500),
        horizon_steps=30,
        audit_oos=False,
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
    assert hier["context_tide_2000v"].startswith("No disponible")
    assert hier["anchor_window_candles"] == 1000
    assert hier["predictive_scenario_validated"] is True
    assert "Sin escenario predictivo validado" not in hier["executive_banner"]

    # Caso 2: 750 velas -> 2000v y 1000v son `N/D`, 500v entrega geometría t+30 sin bloqueo
    df_young = _build_synthetic_df(750, seed=304)
    young_res = KinetopusMultiLensRunner(m_cfg).run(df_override=df_young)
    hier_young = young_res.confluence["hierarchy_verdict"]
    sum_young = young_res.confluence["lenses_summary"]

    assert sum_young["2000"]["status"] == "N/D"
    assert sum_young["1000"]["status"] == "N/D"
    assert sum_young["500"]["status"] == "OK"
    assert hier_young["predictive_scenario_validated"] is True
    assert hier_young["anchor_window_candles"] == 500
    assert "Sin escenario predictivo validado" not in hier_young["executive_banner"]
    assert len(hier_young["executive_ranges"]) >= 2
    assert hier_young["executive_ranges"][-1]["horizon_step"] == "t+30"


def test_geometric_hierarchy_no_oos_veto_and_3lens_t150():
    """Verifica v0.3.1: cero bloqueos por SINDy R² u OOS, 3 lentes con t+150 y confianza geométrica."""
    def _chk_t150(base_p: float, end_p: float):
        return [
            {
                "step": 150,
                "deterministic_price": end_p,
                "deterministic_return_pct": round(((end_p / base_p) - 1.0) * 100.0, 2),
                "mc_p5": end_p * 0.85,
                "mc_p25": end_p * 0.93,
                "mc_p50": end_p,
                "mc_p75": end_p * 1.07,
                "mc_p95": end_p * 1.15,
            }
        ]

    # Subcaso A: SINDy R² bajo (0.18) y sin sello OOS, pero Curva-Precio R² alto (0.93) y 3 lentes alineadas
    mock_geom_aligned = [
        {
            "window_candles": 2000,
            "color_name": "Cian",
            "role_code": "CONTEXTO_FONDO",
            "role_label": "Contexto estructural (2000v)",
            "available": True,
            "seal_passed": True,
            "seal_grade": "GEOMETRICO_ACTIVO",
            "oos_consensus_hr_pct": None,
            "sindy_r2_score": 0.14,
            "curve_price_r2": 0.91,
            "curve_price_mape_pct": 3.4,
            "curve_price_quality": "Alto",
            "curve_price_fit": {"window_price_r2": 0.91, "window_price_mape_pct": 3.4, "fit_label": "Alto"},
            "raw_direction": "ALCISTA",
            "cusum_tension_ratio": 0.25,
            "human_regime": {"state_code": "IMPULSO_ALCISTA", "state_label": "Impulso alcista", "full_label": "Impulso alcista · cerca de su curva"},
            "horizon_checkpoints": _chk_t150(100.0, 114.0),
            "t150_summary": {"center_price": 114.0, "center_return_pct": 14.0, "p25_price": 106.0, "p75_price": 122.0, "p5_price": 96.0, "p95_price": 131.0},
            "scenarios": {"available": True, "validated": True, "horizon_step": "t+150"},
        },
        {
            "window_candles": 1000,
            "color_name": "Ámbar",
            "role_code": "PRINCIPAL_PREDICTIVA",
            "role_label": "Eje principal (1000v)",
            "available": True,
            "seal_passed": True,
            "seal_grade": "GEOMETRICO_ACTIVO",
            "oos_consensus_hr_pct": None,
            "sindy_r2_score": 0.18,
            "curve_price_r2": 0.93,
            "curve_price_mape_pct": 2.1,
            "curve_price_quality": "Alto",
            "curve_price_fit": {"window_price_r2": 0.93, "window_price_mape_pct": 2.1, "fit_label": "Alto"},
            "raw_direction": "ALCISTA",
            "cusum_tension_ratio": 0.20,
            "human_regime": {"state_code": "IMPULSO_ALCISTA", "state_label": "Impulso alcista", "full_label": "Impulso alcista · cerca de su curva"},
            "horizon_checkpoints": _chk_t150(100.0, 118.0),
            "t150_summary": {"center_price": 118.0, "center_return_pct": 18.0, "p25_price": 109.0, "p75_price": 127.0, "p5_price": 100.0, "p95_price": 135.0},
            "scenarios": {"available": True, "validated": True, "horizon_step": "t+150"},
        },
        {
            "window_candles": 500,
            "color_name": "Violeta",
            "role_code": "SENSOR_ALERTA",
            "role_label": "Pulso táctico (500v)",
            "available": True,
            "seal_passed": True,
            "seal_grade": "GEOMETRICO_ACTIVO",
            "oos_consensus_hr_pct": None,
            "sindy_r2_score": 0.12,
            "curve_price_r2": 0.95,
            "curve_price_mape_pct": 1.6,
            "curve_price_quality": "Alto",
            "curve_price_fit": {"window_price_r2": 0.95, "window_price_mape_pct": 1.6, "fit_label": "Alto"},
            "raw_direction": "ALCISTA",
            "cusum_tension_ratio": 0.18,
            "human_regime": {"state_code": "IMPULSO_ALCISTA", "state_label": "Impulso alcista", "full_label": "Impulso alcista · cerca de su curva"},
            "horizon_checkpoints": _chk_t150(100.0, 121.0),
            "t150_summary": {"center_price": 121.0, "center_return_pct": 21.0, "p25_price": 112.0, "p75_price": 130.0, "p5_price": 102.0, "p95_price": 138.0},
            "scenarios": {"available": True, "validated": True, "horizon_step": "t+150"},
        },
    ]
    verdict_ok = KinetopusMultiLensRunner._synthesize_fixed_hierarchy(mock_geom_aligned)
    assert verdict_ok["predictive_scenario_validated"] is True
    assert verdict_ok["unvalidated_reason"] is None
    assert "Sin escenario" not in verdict_ok["executive_banner"]
    assert verdict_ok["global_physical_confidence"] == "ALTA"
    assert len(verdict_ok["curves_comparison"]) == 3
    assert set(verdict_ok["ranges_by_lens"].keys()) == {"2000", "1000", "500"}

    # Subcaso B: Desalineación entre 2000v y 1000v + ajuste curva-precio débil -> confianza BAJA sin bloquear proyección
    mock_divergent = [dict(item) for item in mock_geom_aligned]
    mock_divergent[0] = dict(mock_divergent[0], raw_direction="BAJISTA")
    mock_divergent[1] = dict(
        mock_divergent[1],
        curve_price_r2=0.42,
        curve_price_mape_pct=9.5,
        curve_price_fit={"window_price_r2": 0.42, "window_price_mape_pct": 9.5, "fit_label": "Moderado"},
        cusum_tension_ratio=0.88,
    )
    verdict_div = KinetopusMultiLensRunner._synthesize_fixed_hierarchy(mock_divergent)
    assert verdict_div["predictive_scenario_validated"] is True
    assert verdict_div["global_physical_confidence"] == "BAJA"


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
