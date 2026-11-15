#!/usr/bin/env python3
"""
CLI Estandarizado en Dos Etapas (v0.3.1) — KineTopus-Analyst (`kinetopus_pro`).

Flujo de dos etapas con enfoque geométrico puro y cifras 100% blindadas:
  - Etapa 1 (Cuantitativa pura, funciona sin IA):
      `python -m kinetopus_pro.cli --ticker BTC-USD --interval 1d`
      Ejecuta las 3 lentes (`2000v` Cian / `1000v` Ámbar / `500v` Violeta) proyectando SIEMPRE
      `t+150` en todas (Walk-Forward OOS desactivado por defecto salvo `--audit-oos`), genera
      `confluence.json`, `report_bundle.npz` (100% del historial descargado), `hero.png`
      (+ alias `confluence.png`), los 3 `lens_<W>/dashboard.png` + 18 `panels/*.png`,
      `narrative_template.json` y el `report.html` interactivo + `analysis.md`.
  - Etapa 2 (Re-renderizado instantáneo <0.5 s con narrativa cualitativa):
      `python -m kinetopus_pro.cli --render-report <DIR> [--artifact-dir <ART_DIR>]`
      Fusiona `<DIR>/narrative.json` (solo texto cualitativo escrito por el agente) con las
      cifras exactas del motor para actualizar `report.html` y `analysis.md`.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent

from kinetopus_pro.headless_pipeline import KinetopusAnalysisConfig, KinetopusHeadlessPipeline
from kinetopus_pro.multi_lens import DEFAULT_MULTI_LENSES, KinetopusMultiLensRunner, MultiLensConfig
from kinetopus_pro.report_builder import KinetopusReportBuilder
from kinetopus_pro.static_renderer import KinetopusStaticRenderer


def sanitize_ticker_folder(raw_name: str) -> str:
    """Convierte símbolos con caracteres especiales (ej. GC=F, ^GSPC, BTC-USD) en carpetas seguras."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name.strip())
    return cleaned.strip("_") or "CUSTOM_ASSET"


def parse_lenses_arg(raw_lenses: str) -> Tuple[int, ...]:
    parts = [int(p.strip()) for p in raw_lenses.split(",") if p.strip()]
    if len(parts) != 3 or any(w <= 20 for w in parts):
        raise argparse.ArgumentTypeError(
            "Se requieren exactamente 3 enteros positivos (>20) separados por coma, p. ej. '2000,1000,500'."
        )
    return tuple(sorted(parts, reverse=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta el análisis físico-geométrico Multi-Lente KineTopus (v0.3.1) o re-renderiza Etapa 2."
    )
    parser.add_argument("--ticker", type=str, default="BTC-USD", help="Símbolo en Yahoo Finance (default: BTC-USD).")
    parser.add_argument(
        "--period",
        type=str,
        default="10y",
        help="Periodo base de descarga: 1mo..10y, max (default: 10y, con respaldo automático a 'max' en modo multi-lente).",
    )
    parser.add_argument("--interval", type=str, default="1d", help="Resolución de vela: 1h, 1d, 1wk, 1mo (default: 1d).")
    parser.add_argument(
        "--lenses",
        type=parse_lenses_arg,
        default=DEFAULT_MULTI_LENSES,
        help="Tres ventanas jerárquicas separadas por coma: Contexto,Principal,Alerta (default: 2000,1000,500).",
    )
    parser.add_argument(
        "--single-lens",
        action="store_true",
        help="Ejecuta una única ventana (`--context-window`) en lugar del modo Multi-Lente por defecto.",
    )
    parser.add_argument("--context-window", type=int, default=1000, help="Ventana activa para `--single-lens` (default: 1000).")
    parser.add_argument("--horizon", type=int, default=150, help="Horizonte predictivo t+N en velas (default: 150).")
    parser.add_argument("--smooth-tol", type=float, default=0.0050, help="Tolerancia inicial del Spline C² (default: 0.0050).")
    parser.add_argument("--cusum-k", type=float, default=None, help="Drift CUSUM manual (por defecto se auto-calibra por lente).")
    parser.add_argument("--cusum-h", type=float, default=5.0, help="Umbral crítico H de quiebre CUSUM (default: 5.0).")
    parser.add_argument("--poly-degree", type=int, default=1, choices=[1, 2, 3], help="Grado polinomial SINDy (default: 1).")
    parser.add_argument(
        "--audit-oos",
        action="store_true",
        help="Activa opcionalmente la auditoría Walk-Forward OOS (desactivada por defecto en v0.3.1).",
    )
    parser.add_argument(
        "--wf-cuts",
        type=int,
        default=0,
        help="Cortes objetivo Walk-Forward OOS (default: 0 desactivado; --audit-oos usa 10 cortes o el número aquí indicado).",
    )
    parser.add_argument("--min-wf-cuts", type=int, default=5, help="Mínimo de cortes efectivos OOS informativos (default: 5).")
    parser.add_argument("--no-max-fallback", action="store_true", help="Desactiva la ampliación automática de '10y' a 'max'.")
    parser.add_argument("--no-parallel", action="store_true", help="Ejecuta las 3 lentes de forma secuencial en lugar de paralela.")
    parser.add_argument("--no-auto-tune", action="store_true", help="Desactiva la calibración automática CUSUMAutoTuner.")
    parser.add_argument("--no-auto-rescue", action="store_true", help="Desactiva el rescate automático Autopilot 2D.")
    parser.add_argument("--classic-price", action="store_true", help="Modo Física Clásica: usa P(t) directo en lugar de retornos logarítmicos.")
    parser.add_argument("--disable-norm", action="store_true", help="Desactiva normalización Z-Score (sistemas sintéticos ideales).")
    parser.add_argument("--csv", type=str, default=None, help="Ruta opcional a un archivo CSV local en vez de Yahoo Finance.")
    parser.add_argument("--output-dir", type=str, default=None, help="Directorio de salida (default: reports/<TICKER>/<TIMESTAMP>/).")
    parser.add_argument(
        "--render-report",
        type=str,
        default=None,
        help="Etapa 2: Ruta a un directorio de corrida existente para re-renderizar report.html y analysis.md con narrative.json.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=str,
        default=None,
        help="Directorio opcional donde copiar hero.png, los 3 dashboards (2000v/1000v/500v), report.html y el Markdown con rutas absolutas.",
    )
    parser.add_argument(
        "--artifact-slug",
        type=str,
        default=None,
        help="Prefijo opcional para los archivos copiados en `--artifact-dir` (ej. btc_usd_v3).",
    )
    return parser.parse_args()


def _run_render_stage2_mode(args: argparse.Namespace) -> int:
    rep_dir = Path(args.render_report).resolve()
    if not rep_dir.is_dir():
        print(f"[ERROR] No existe el directorio de reporte: {rep_dir}", file=sys.stderr)
        return 1
    art_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else None
    rendered = KinetopusReportBuilder.render_from_directory(
        report_dir=rep_dir,
        artifact_dir=art_dir,
        artifact_slug=args.artifact_slug,
    )
    out_summary = {
        "status": "OK",
        "mode": "render_report_stage2",
        "report_dir": str(rep_dir),
        **rendered,
    }
    print(json.dumps(out_summary, indent=2, ensure_ascii=False))
    return 0


def _run_single_lens_mode(args: argparse.Namespace, ticker_label: str, df_override: Any, out_dir: Path) -> int:
    audit_oos = bool(args.audit_oos or args.wf_cuts > 0)
    cfg = KinetopusAnalysisConfig(
        ticker=ticker_label,
        period=args.period,
        interval=args.interval,
        context_window=args.context_window,
        horizon_steps=args.horizon,
        smooth_tol=args.smooth_tol,
        cusum_k=args.cusum_k,
        cusum_h=args.cusum_h,
        poly_degree=args.poly_degree,
        disable_norm=args.disable_norm,
        disable_returns=args.classic_price,
        auto_tune=not args.no_auto_tune,
        auto_rescue=not args.no_auto_rescue,
        audit_oos=audit_oos,
        wf_cuts=args.wf_cuts,
        strict_wf_window=True,
        min_wf_effective_cuts=args.min_wf_cuts,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "telemetry.json"
    png_path = out_dir / "dashboard.png"
    panels_dir = out_dir / "panels"

    with contextlib.redirect_stdout(sys.stderr):
        result = KinetopusHeadlessPipeline(cfg).run(df_override=df_override)
    dash_abs = KinetopusStaticRenderer.render_dashboard(result, str(png_path))
    panels_map = KinetopusStaticRenderer.render_individual_panels(result, str(panels_dir))

    result.telemetry["artifacts"] = {
        "report_dir": str(out_dir),
        "telemetry_json": str(json_path),
        "dashboard_png": dash_abs,
        "panels_dir": str(panels_dir),
        "individual_panels": panels_map,
        "expected_analysis_md": str(out_dir / "analysis.md"),
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result.telemetry, f, indent=2, ensure_ascii=False)

    kpis = result.telemetry["executive_kpis"]
    ds = result.telemetry["metadata"]["dataset"]
    cal = result.telemetry["calibration"]
    wf = result.telemetry["reliability_seal"]["mini_walk_forward_oos"]

    summary = {
        "status": "OK",
        "mode": "single_lens",
        "ticker": ds["ticker"],
        "last_date": ds["last_candle_date"],
        "last_close": ds["last_close_price"],
        "calibrated_k": cal["effective_cusum_k"],
        "effective_tol": cal["effective_smooth_tol"],
        "human_regime": result.telemetry.get("human_regime", {}).get("full_label"),
        "directional_inertia": kpis["directional_inertia"],
        "curve_price_r2": kpis.get("curve_price_r2"),
        "curve_price_mape_pct": kpis.get("curve_price_mape_pct"),
        "curve_price_quality": kpis.get("curve_price_quality"),
        "sindy_r2": kpis["sindy_r2_score"],
        "cusum_status": kpis["cusum_semaphore"],
        "oos_enabled": audit_oos,
        "oos_physics_class": wf.get("asset_physics_class"),
        "oos_consensus_hr_pct": wf.get("consensus_hit_ratio_pct"),
        "oos_effective_cuts": wf.get("effective_cuts"),
        "overall_confidence": kpis["overall_physical_confidence"],
        "report_dir": str(out_dir),
        "telemetry_json": str(json_path),
        "dashboard_png": dash_abs,
        "panels_dir": str(panels_dir),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    args = parse_args()

    if args.render_report:
        return _run_render_stage2_mode(args)

    df_override = None
    ticker_label = args.ticker
    if args.csv:
        csv_path = Path(args.csv).resolve()
        if not csv_path.is_file():
            print(f"[ERROR] No existe el archivo CSV: {csv_path}", file=sys.stderr)
            return 1
        df_override = pd.read_csv(csv_path)
        if args.ticker == "BTC-USD":
            ticker_label = csv_path.stem.upper()

    if args.output_dir:
        out_dir = Path(args.output_dir).resolve()
    else:
        ts_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_ticker = sanitize_ticker_folder(ticker_label)
        base_root = REPO_ROOT if (REPO_ROOT / "pyproject.toml").is_file() else Path.cwd()
        out_dir = base_root / "reports" / safe_ticker / ts_str

    if args.single_lens:
        return _run_single_lens_mode(args, ticker_label, df_override, out_dir)

    m_cfg = MultiLensConfig(
        ticker=ticker_label,
        base_period=args.period,
        fallback_period="" if args.no_max_fallback else "max",
        interval=args.interval,
        lenses=args.lenses,
        horizon_steps=args.horizon,
        smooth_tol=args.smooth_tol,
        cusum_k=args.cusum_k,
        cusum_h=args.cusum_h,
        poly_degree=args.poly_degree,
        disable_norm=args.disable_norm,
        disable_returns=args.classic_price,
        auto_tune=not args.no_auto_tune,
        auto_rescue=not args.no_auto_rescue,
        audit_oos=bool(args.audit_oos or args.wf_cuts > 0),
        wf_cuts=args.wf_cuts,
        min_wf_effective_cuts=args.min_wf_cuts,
        parallel=not args.no_parallel,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    runner = KinetopusMultiLensRunner(m_cfg)
    multi_res = runner.run(df_override=df_override)

    hero_png_path = out_dir / "hero.png"
    conf_png_path = out_dir / "confluence.png"
    conf_json_path = out_dir / "confluence.json"

    KinetopusStaticRenderer.render_hero_chart(multi_res, str(hero_png_path))
    shutil.copy2(hero_png_path, conf_png_path)

    lens_artifacts: Dict[str, Any] = {}
    for slot in multi_res.lens_slots:
        w_key = str(slot.window_candles)
        if not slot.available or slot.run_result is None:
            lens_artifacts[w_key] = {
                "status": "N/D",
                "reason": slot.unavailable_reason,
            }
            continue

        lens_dir = out_dir / f"lens_{slot.window_candles}"
        lens_dir.mkdir(parents=True, exist_ok=True)
        l_json = lens_dir / "telemetry.json"
        l_dash = lens_dir / "dashboard.png"
        l_panels_dir = lens_dir / "panels"

        dash_abs = KinetopusStaticRenderer.render_dashboard(slot.run_result, str(l_dash))
        panels_map = KinetopusStaticRenderer.render_individual_panels(slot.run_result, str(l_panels_dir))

        slot.run_result.telemetry["artifacts"] = {
            "lens_dir": str(lens_dir),
            "telemetry_json": str(l_json),
            "dashboard_png": dash_abs,
            "panels_dir": str(l_panels_dir),
            "individual_panels": panels_map,
        }
        with open(l_json, "w", encoding="utf-8") as f:
            json.dump(slot.run_result.telemetry, f, indent=2, ensure_ascii=False)

        lens_artifacts[w_key] = {
            "status": "OK",
            "lens_dir": str(lens_dir),
            "telemetry_json": str(l_json),
            "dashboard_png": dash_abs,
            "panels_dir": str(l_panels_dir),
            "individual_panels": panels_map,
        }

    bundle_npz_path = KinetopusReportBuilder.save_report_bundle(multi_res, out_dir)
    nav_tpl_path = KinetopusReportBuilder.write_narrative_template(out_dir, multi_res.confluence)

    multi_res.confluence["artifacts"] = {
        "report_dir": str(out_dir),
        "confluence_json": str(conf_json_path),
        "hero_png": str(hero_png_path),
        "confluence_png": str(conf_png_path),
        "report_bundle_npz": str(bundle_npz_path),
        "narrative_template_json": str(nav_tpl_path),
        "report_html": str(out_dir / "report.html"),
        "analysis_md": str(out_dir / "analysis.md"),
        "lenses": lens_artifacts,
    }

    with open(conf_json_path, "w", encoding="utf-8") as f:
        json.dump(multi_res.confluence, f, indent=2, ensure_ascii=False)

    art_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else None
    rendered_docs = KinetopusReportBuilder.render_from_directory(
        report_dir=out_dir,
        artifact_dir=art_dir,
        artifact_slug=args.artifact_slug,
    )

    ds = multi_res.confluence["metadata"]["dataset"]
    dl = multi_res.confluence["metadata"]["download"]
    hier = multi_res.confluence["hierarchy_verdict"]

    summary = {
        "status": "OK",
        "mode": "multi_lens",
        "ticker": ds["ticker"],
        "last_date": ds["last_candle_date"],
        "last_close": ds["last_close_price"],
        "download_period_used": dl["effective_period_used"],
        "fallback_to_max_triggered": dl["fallback_to_max_triggered"],
        "total_downloaded_candles": ds["total_downloaded_candles"],
        "hierarchy_verdict": hier,
        "report_dir": str(out_dir),
        "confluence_json": str(conf_json_path),
        "hero_png": str(hero_png_path),
        "confluence_png": str(conf_png_path),
        "report_bundle_npz": str(bundle_npz_path),
        "narrative_template_json": str(nav_tpl_path),
        "report_html": rendered_docs["report_html"],
        "analysis_md": rendered_docs["analysis_md"],
        "telemetry_json": str(conf_json_path),
        "dashboard_png": str(hero_png_path),
        "lenses": lens_artifacts,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
