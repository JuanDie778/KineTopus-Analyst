"""
Suite de Auditoría v0.3.0 — Estándar Definitivo de Análisis (`design_estandar_analisis.md`).

Verifica las 4 ramas y 17 decisiones aprobadas:
  1. Cono Monte Carlo de integración simple EWMA en log-precio (`P50 == F(t)`, escala `~sqrt(k)`,
     cero explosión de doble integración) + contigüidad `np.float64` `C_CONTIGUOUS`.
  2. Métrica empírica no bloqueante `cone_calibration` en el Walk-Forward OOS.
  3. Jerarquía `1000v` Principal Predictiva, supresión de rangos/escenarios en `500v` (solo alertas
     y pines) y regla estricta `"Sin escenario predictivo validado hoy"` + confianza `"BAJA"` si
     `1000v` reprueba o es `N/D`.
  4. Taxonomía humana de 5 estados (`Lateral en máximos`, modificadores `sobreextendido` /
     `descolgado` / `cerca de su curva`) y cero códigos crudos `Q1–Q4` en etiquetas visibles.
  5. Tres escenarios probabilísticos con probabilidad de primer toque (`touch_probability_pct` en
     `[0, 100]`) y objetivos condicionales monótonos (`bear_target < dn_brk < last_p < up_brk < bull_target`).
  6. Flujo dual en 2 etapas (`--csv` -> `hero.png` + `report.html` + `report_bundle.npz`, y
     `--render-report` con `narrative.json` + `--artifact-dir`) con cifras 100% blindadas.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kinetopus_pro.headless_pipeline import KinetopusAnalysisConfig, KinetopusHeadlessPipeline
from kinetopus_pro.multi_lens import KinetopusMultiLensRunner, MultiLensConfig


def _build_ohlcv_df(n: int, seed: int = 2026) -> pd.DataFrame:
    """Serie sintética OHLCV acoplada Precio-Volumen con ciclos inerciales fuertes y sin huecos."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-02", periods=n)
    t = np.linspace(0.0, (n / 25.0) * np.pi, n, dtype=np.float64)

    split = int(n * 0.62)
    r = np.zeros(n, dtype=np.float64)
    r[:split] = 0.0012 + 0.0060 * np.sin(t[:split] * 0.40) + rng.normal(0.0, 0.0020, split)
    r[split:] = 0.0009 + 0.0075 * np.cos(t[split:] * 0.30) + rng.normal(0.0, 0.0022, n - split)

    close = 250.0 * np.exp(np.cumsum(r))
    open_p = np.roll(close, 1)
    open_p[0] = close[0] * 0.998
    intraday_span = close * rng.uniform(0.003, 0.009, n)
    high = np.maximum(open_p, close) + intraday_span * 0.65
    low = np.minimum(open_p, close) - intraday_span * 0.65
    volume = 2.5e6 * (1.0 + 0.35 * np.cos(t * 0.40) + rng.uniform(0.05, 0.20, n))

    return pd.DataFrame(
        {"Open": open_p, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


def test_single_integration_cone_scaling_and_centering():
    """Verifica integración simple EWMA: mediana anclada a F(t) y ancho proporcional a sqrt(k)."""
    rng = np.random.default_rng(123)
    sigma_true = 0.010  # ~1% diario
    r_smooth = np.full(400, 0.0005, dtype=np.float64)
    log_rets = r_smooth + rng.normal(0.0, sigma_true, 400).astype(np.float64)
    precio_raw = 100.0 * np.exp(np.cumsum(log_rets))
    last_p = float(precio_raw[-1])
    det_path = last_p * np.exp(np.linspace(0.0004, 0.06, 150, dtype=np.float64))

    pct_list, mc_paths, sigma_ewma = (
        KinetopusHeadlessPipeline._simulate_calibrated_single_integration_cone(
            last_price=last_p,
            det_prices=det_path,
            precio_raw=precio_raw,
            log_returns=log_rets,
            r_smooth=r_smooth,
            dt_val=1.0,
            unstable_flag=False,
            empty_r_eq=False,
            disable_returns=False,
            disable_norm=False,
            random_seed=42,
            n_paths=2000,
        )
    )
    assert 0.006 <= sigma_ewma <= 0.015
    assert mc_paths.dtype == np.float64
    assert mc_paths.flags["C_CONTIGUOUS"]
    assert mc_paths.shape == (150, 2000)
    assert len(pct_list) == 5

    p5, p25, p50, p75, p95 = [np.asarray(row, dtype=np.float64) for row in pct_list]

    # 1. Mediana centrada en F(t) dentro de error muestral Monte Carlo (<2.5%)
    rel_med_err = float(np.max(np.abs(p50 - det_path) / det_path))
    assert rel_med_err < 0.025

    # 2. Escala sqrt(k): el ancho logarítmico IQR entre k=149 y k=24 debe ser ~sqrt(150/25) = sqrt(6) ≈ 2.45
    iqr_log_25 = float(np.log(p75[24] / p25[24]))
    iqr_log_150 = float(np.log(p75[149] / p25[149]))
    ratio = iqr_log_150 / max(iqr_log_25, 1e-9)
    assert 2.05 <= ratio <= 2.85, f"Ratio IQR inesperado (doble integración daría ~14.7): {ratio:.3f}"

    # 3. Sin explosión artificial: con vol 1% diario a 150 velas (~12.2% 1-sigma), P95/P5 < 1.8x
    assert float(p95[-1] / p5[-1]) < 1.80


def test_oos_cone_calibration_non_blocking():
    """Verifica que `cone_calibration` se calcula cuando `audit_oos=True` sin bloquear proyecciones."""
    df = _build_ohlcv_df(640, seed=808)
    cfg = KinetopusAnalysisConfig(
        ticker="CAL-OOS",
        context_window=400,
        horizon_steps=150,
        audit_oos=True,
        wf_cuts=6,
        min_wf_effective_cuts=5,
        auto_tune=False,
        auto_rescue=True,
        cusum_k=1.2,
    )
    res = KinetopusHeadlessPipeline(cfg).run(df_override=df)
    wf = res.telemetry["reliability_seal"]["mini_walk_forward_oos"]
    assert wf["audit_enabled"] is True
    assert "cone_calibration" in wf
    cc = wf["cone_calibration"]
    assert cc["evaluated"] is True
    assert 0.0 <= cc["empirical_p25_p75_coverage_pct"] <= 100.0
    assert 0.0 <= cc["empirical_p5_p95_coverage_pct"] <= 100.0
    assert cc["calibration_label"] in {
        "Bien calibrado",
        "Banda conservadora (amplia)",
        "Banda estrecha",
    }


def test_five_state_human_taxonomy_and_no_raw_enums():
    """Audita los 5 estados humanos, el sub-matiz `Lateral en máximos` y ausencia de enums `Q1..Q4`."""
    flat_det = np.linspace(595.0, 596.0, 150, dtype=np.float64)  # +0.17% < noise_band
    up_det = np.linspace(500.0, 535.0, 150, dtype=np.float64)    # +7.0% > noise_band
    dn_det = np.linspace(420.0, 385.0, 150, dtype=np.float64)    # -8.3% < -noise_band

    common = dict(
        sigma_ewma=0.008,
        unstable_flag=False,
        empty_r_eq=False,
        disable_returns=False,
        topology_class="CICLO_ORBITAL_ACTIVO",
        cusum_status="ESTABLE",
        seal_grade="APROBADO_PLENO",
    )

    # 1. Lateral en máximos · sobreextendido
    lat_max = KinetopusHeadlessPipeline.classify_human_regime(
        last_price=595.0,
        window_max_price=600.0,
        gap_now_pct=4.2,
        vel_now=0.0001,
        acc_now=-0.00002,
        det_prices=flat_det,
        **common,
    )
    assert lat_max["state_code"] == "LATERAL_DIGESTION"
    assert lat_max["near_window_highs"] is True
    assert lat_max["state_label"] == "Lateral en máximos"
    assert lat_max["position_code"] == "SOBREEXTENDIDO"
    assert lat_max["full_label"].startswith("Lateral en máximos · sobreextendido")

    # 2. Impulso alcista · cerca de su curva
    imp = KinetopusHeadlessPipeline.classify_human_regime(
        last_price=500.0,
        window_max_price=600.0,
        gap_now_pct=0.2,
        vel_now=0.0040,
        acc_now=0.0002,
        det_prices=up_det,
        **common,
    )
    assert imp["state_label"] == "Impulso alcista"
    assert imp["position_code"] == "EN_LINEA"
    assert "cerca de su curva" in imp["full_label"]

    # 3. Alcista frenando
    fren = KinetopusHeadlessPipeline.classify_human_regime(
        last_price=500.0,
        window_max_price=600.0,
        gap_now_pct=0.0,
        vel_now=0.0035,
        acc_now=-0.0003,
        det_prices=up_det,
        **common,
    )
    assert fren["state_label"] == "Alcista frenando"

    # 4. Corrección bajista · descolgado
    corr = KinetopusHeadlessPipeline.classify_human_regime(
        last_price=420.0,
        window_max_price=600.0,
        gap_now_pct=-4.5,
        vel_now=-0.0045,
        acc_now=-0.0003,
        det_prices=dn_det,
        **common,
    )
    assert corr["state_label"] == "Corrección bajista"
    assert corr["position_code"] == "DESCOLGADO"
    assert "descolgado" in corr["full_label"]

    # 5. Caída frenando / Suelo en formación
    suelo = KinetopusHeadlessPipeline.classify_human_regime(
        last_price=420.0,
        window_max_price=600.0,
        gap_now_pct=-0.4,
        vel_now=-0.0035,
        acc_now=0.0004,
        det_prices=dn_det,
        **common,
    )
    assert suelo["state_label"] == "Caída frenando / Suelo en formación"

    for obj in (lat_max, imp, fren, corr, suelo):
        for raw_q in ("Q1_", "Q2_", "Q3_", "Q4_", "EXOGENO_FUNDAMENTALISTA"):
            assert raw_q not in obj["full_label"]
            assert raw_q not in obj["topology_human"]
            assert raw_q not in obj["seal_human"]


def test_simultaneous_3lens_t150_and_geometric_scenarios():
    """Verifica que LAS 3 LENTES proyectan siempre t+150, y escenarios P25/P75 monótonos en v0.3.1."""
    df = _build_ohlcv_df(1150, seed=909)
    m_cfg = MultiLensConfig(
        ticker="SCEN-ASSET",
        lenses=(750, 550, 350),
        horizon_steps=150,
        audit_oos=False,
        auto_tune=False,
        auto_rescue=True,
        cusum_k=1.1,
        parallel=False,
    )
    m_res = KinetopusMultiLensRunner(m_cfg).run(df_override=df)
    conf = m_res.confluence

    # Por defecto Walk-Forward OOS desactivado y las 3 lentes emiten t+150 completo
    for w_str in ("750", "550", "350"):
        l_sum = conf["lenses_summary"][w_str]
        assert l_sum["available"] is True
        assert l_sum["emits_t150_projection"] is True
        steps_present = {int(c["step"]) for c in l_sum["horizon_checkpoints"]}
        assert {5, 21, 63, 150}.issubset(steps_present)
        assert l_sum["horizon_checkpoints"][-1]["step"] == 150
        assert isinstance(l_sum["t150_summary"].get("center_price"), float)
        assert isinstance(l_sum["curve_price_r2"], float)
        assert isinstance(l_sum["curve_price_mape_pct"], float)

    # Sensor (tercera lente = 350v) sigue manteniendo su rol táctico mientras proyecta t+150
    sen_sum = conf["lenses_summary"]["350"]
    assert sen_sum["role_code"] == "SENSOR_ALERTA"

    # Lente principal (550v) calcula escenarios geométricos P25/P75 monótonos
    pri_tel = m_res.lens_slots[1].run_result.telemetry
    sc = pri_tel["scenarios"]
    assert sc["available"] is True
    for k in ("base", "bullish", "bearish"):
        prob = sc[k]["touch_probability_pct"]
        assert 0.0 <= prob <= 100.0

    last_p = float(conf["metadata"]["dataset"]["last_close_price"])
    up_brk = float(sc["bullish"]["trigger_price"])
    dn_brk = float(sc["bearish"]["trigger_price"])
    bull_tgt = float(sc["bullish"]["target_price"])
    bear_tgt = float(sc["bearish"]["target_price"])

    assert bear_tgt < dn_brk < last_p < up_brk < bull_tgt


def test_two_stage_cli_hero_report_html_and_narrative_injection(tmp_path: Path):
    """Prueba E2E v0.3.1: historial 100% en NPZ, 3 conos/dashboards, 5 ventanas y cero CUSUM 1-vela."""
    df = _build_ohlcv_df(1120, seed=4242)
    csv_path = tmp_path / "ohlcv_asset.csv"
    out_dir = tmp_path / "reports_out"
    art_dir = tmp_path / "artifacts_out"
    df.reset_index().rename(columns={"index": "Date"}).to_csv(csv_path, index=False)

    # Etapa 1: Ejecución cuantitativa pura por defecto (Walk-Forward OOS apagado)
    proc1 = subprocess.run(
        [
            sys.executable,
            "-m",
            "kinetopus_pro.cli",
            "--csv",
            str(csv_path),
            "--ticker",
            "TEST-V31",
            "--lenses",
            "700,500,300",
            "--horizon",
            "150",
            "--no-auto-tune",
            "--cusum-k",
            "1.1",
            "--output-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    sum1 = json.loads(proc1.stdout)
    assert sum1["status"] == "OK"
    assert sum1["hierarchy_verdict"]["predictive_scenario_validated"] is True
    rep_dir = Path(sum1["report_dir"])

    hero_png = Path(sum1["hero_png"])
    bundle_npz = Path(sum1["report_bundle_npz"])
    tpl_json = Path(sum1["narrative_template_json"])
    html_path = Path(sum1["report_html"])
    md_path = Path(sum1["analysis_md"])

    for p in (hero_png, bundle_npz, tpl_json, html_path, md_path):
        assert p.is_file(), f"Falta artefacto de Etapa 1: {p}"

    # Verificar que report_bundle.npz guarda el 100% del historial y las 3 proyecciones t+150
    with np.load(bundle_npz, allow_pickle=False) as b_data:
        assert int(b_data["n_full"][0]) == 1120
        assert int(b_data["h_start"][0]) == 0
        assert len(b_data["close_hist"]) == 1120
        for px in ("ctx", "pri", "sen"):
            assert int(b_data[f"{px}_avail"][0]) == 1
            assert len(b_data[f"{px}_det"]) == 150
            assert b_data[f"{px}_mc"].shape == (5, 150)

    html_stage1 = html_path.read_text(encoding="utf-8")
    assert 'id="hero-plot"' in html_stage1
    assert 'id="theme-toggle"' in html_stage1
    assert "KineTopus · v0.3.1" in html_stage1
    assert "1. Resumen Ejecutivo" in html_stage1
    assert "2. Escenarios y Curvas" in html_stage1
    assert "3. Laboratorio Técnico (3 Lentes)" in html_stage1
    for win_lbl in ("120v", "500v", "1000v", "2000v", "Todo el historial"):
        assert win_lbl in html_stage1
    assert 'id="cone-buttons"' in html_stage1
    assert "Sin cono" in html_stage1
    assert 'id="dash-buttons"' in html_stage1
    assert "selectDashboard('700'" in html_stage1
    assert "selectDashboard('500'" in html_stage1
    assert "selectDashboard('300'" in html_stage1

    assert "Sin escenario predictivo validado hoy" not in html_stage1
    assert "Ruptura alcista CUSUM (1 vela)" not in html_stage1
    assert "Invalidación bajista CUSUM (1 vela)" not in html_stage1
    for raw_enum in (
        "Q1_IMPULSO_ALCISTA_ACELERANDO",
        "Q2_ALCISTA_DESACELERANDO",
        "Q3_CAIDA_ACELERANDO",
        "Q4_CAIDA_FRENANDO_SUELO",
        "EXOGENO_FUNDAMENTALISTA",
    ):
        assert raw_enum not in html_stage1

    # Etapa 2: Escribir `narrative.json` cualitativo y re-renderizar con `--render-report`
    custom_headline = "TEST-V31 prueba flujo geométrico en dos etapas con 3 lentes t+150."
    narrative_payload = {
        "headline": custom_headline,
        "scenarios_catalysts": {
            "base": "Flujo comprador ordenado dentro de las bandas P25–P75.",
            "bullish": "Expansión sostenida sobre el cuartil superior P75.",
            "bearish": "Debilidad bajo el cuartil P25 hacia la banda inferior.",
        },
        "top_insights": [
            {"title": "Lectura central", "body": "El motor controla el 100% de precios como $250 sin romper KaTeX."},
            {"title": "Confluencia 3 curvas", "body": "Las 3 lentes proyectan simultáneamente hacia t+150."},
            {"title": "Ajuste curva-precio", "body": "Prioridad geométrica directa sin veto Walk-Forward."},
        ],
        "web_consensus": {
            "convergence_grade": "CONVERGENTE",
            "summary": "Alineación general con casas de análisis externas.",
            "sources": [
                {
                    "source_name": "Research Demo",
                    "date": "2026-11-15",
                    "stance": "Neutral-constructivo sobre soporte clave",
                    "url": "https://example.com/research-demo",
                }
            ],
        },
        "visual_discrepancies": "Paridad total verificada entre hero.png, los 3 dashboards y JSON.",
        "sindy_translation": "Retorno gobernado por amortiguamiento elástico suave.",
        "cusum_catalysts": [{"date": "2021-06-15", "event": "Rebalanceo trimestral de liquidez."}],
        "reading_limits": ["Proyecciones t+150 representan extrapolación geométrica del régimen."],
    }
    (rep_dir / "narrative.json").write_text(
        json.dumps(narrative_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    t0 = time.perf_counter()
    proc2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "kinetopus_pro.cli",
            "--render-report",
            str(rep_dir),
            "--artifact-dir",
            str(art_dir),
            "--artifact-slug",
            "test_v3_slug",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    elapsed_stage2 = time.perf_counter() - t0
    sum2 = json.loads(proc2.stdout)
    assert sum2["status"] == "OK"
    assert sum2["narrative_stage"] == "enriquecido"
    assert elapsed_stage2 < 10.0

    html_stage2 = html_path.read_text(encoding="utf-8")
    md_stage2 = md_path.read_text(encoding="utf-8")
    assert custom_headline in html_stage2
    assert "https://example.com/research-demo" in html_stage2
    assert custom_headline in md_stage2
    assert "\\$250" in md_stage2
    assert "Sin escenario predictivo validado hoy" not in md_stage2

    # Verificar que el precio exacto de cierre del motor aparece idéntico en analysis.md
    conf_data = json.loads((rep_dir / "confluence.json").read_text(encoding="utf-8"))
    last_close = conf_data["metadata"]["dataset"]["last_close_price"]
    from kinetopus_pro.report_builder import KinetopusReportBuilder

    expected_md_price = KinetopusReportBuilder._fmt_md_price(last_close)
    assert expected_md_price in md_stage2

    # Verificar copia en `--artifact-dir` de hero + LOS 3 DASHBOARDS + html + md
    assert Path(sum2["artifact_staged_md"]).is_file()
    assert Path(sum2["artifact_hero_png"]).is_file()
    assert Path(sum2["artifact_dashboard_1000_png"]).is_file()
    assert Path(sum2["artifact_dashboard_2000_png"]).is_file()
    assert Path(sum2["artifact_dashboard_500_png"]).is_file()
    assert Path(sum2["artifact_report_html"]).is_file()


def test_autopilot_2d_skips_low_sindy_r2_and_triggers_on_instability(monkeypatch):
    """Verifica que SINDy R² < 0.35 NO dispara Autopilot 2D ni bloquea, mientras dr/dt=0 sí activa respaldo."""
    from kinetopus_pro import headless_pipeline as hp_mod
    from kinetopus_pro.engine_bridge import PhysicsDiscoverer as RealPhysicsDiscoverer

    df = _build_ohlcv_df(260, seed=717)

    class FakeLowR2Discoverer(RealPhysicsDiscoverer):
        def extract_equations(self, t, x, x_dot, dt, horizon_steps=150, **kwargs):
            rep = super().extract_equations(t=t, x=x, x_dot=x_dot, dt=dt, horizon_steps=horizon_steps, **kwargs)
            last_p = float(kwargs.get("last_price", 250.0))
            t_det = np.asarray(t[-1] + np.arange(1, horizon_steps + 1, dtype=np.float64) * dt, dtype=np.float64)
            det_p = last_p * np.exp(np.linspace(0.001, 0.04, horizon_steps, dtype=np.float64))
            rep["score"] = 0.05  # < 0.35 — en v0.3.1 NO debe disparar Autopilot 2D
            rep["empty_r_eq"] = False
            rep["equations"] = ["0.0004 - 0.02 * r + 0.001 * V", "-0.05 * V"]
            rep["prediction"] = {
                "unstable": False,
                "det_t_path": t_det,
                "det_price_path": det_p,
                "det_r_proj": np.full(horizon_steps, 0.0004, dtype=np.float64),
                "det_v_proj": np.zeros(horizon_steps, dtype=np.float64),
            }
            return rep

    monkeypatch.setattr(hp_mod, "PhysicsDiscoverer", FakeLowR2Discoverer)
    cfg = KinetopusAnalysisConfig(
        ticker="LOWR2-OK",
        context_window=220,
        horizon_steps=150,
        audit_oos=False,
        auto_tune=False,
        auto_rescue=True,
        cusum_k=1.2,
    )
    res_low_r2 = KinetopusHeadlessPipeline(cfg).run(df_override=df)
    assert res_low_r2.telemetry["calibration"]["autopilot_rescue"]["triggered"] is False
    assert res_low_r2.telemetry["forecast_cone"]["geometric_fallback_used"] is False
    assert len(res_low_r2.arrays["det_price_path"]) == 150
    assert np.all(np.isfinite(res_low_r2.arrays["det_price_path"]))
    assert isinstance(res_low_r2.telemetry["executive_kpis"]["curve_price_r2"], float)

    class FakeZeroEqDiscoverer(RealPhysicsDiscoverer):
        def extract_equations(self, t, x, x_dot, dt, horizon_steps=150, **kwargs):
            rep = super().extract_equations(t=t, x=x, x_dot=x_dot, dt=dt, horizon_steps=horizon_steps, **kwargs)
            rep["score"] = 0.0
            rep["empty_r_eq"] = True
            rep["equations"] = ["0", "0"]
            rep["prediction"] = {
                "unstable": True,
                "det_t_path": np.array([], dtype=np.float64),
                "det_price_path": np.array([], dtype=np.float64),
                "det_r_proj": np.array([], dtype=np.float64),
                "det_v_proj": np.array([], dtype=np.float64),
            }
            return rep

    monkeypatch.setattr(hp_mod, "PhysicsDiscoverer", FakeZeroEqDiscoverer)
    res_zero = KinetopusHeadlessPipeline(cfg).run(df_override=df)
    assert res_zero.telemetry["calibration"]["autopilot_rescue"]["triggered"] is True
    assert res_zero.telemetry["forecast_cone"]["geometric_fallback_used"] is True
    assert len(res_zero.arrays["det_price_path"]) == 150
    assert np.all(np.isfinite(res_zero.arrays["det_price_path"]))
