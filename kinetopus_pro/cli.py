#!/usr/bin/env python3
"""
CLI Estandarizado de Análisis Cuantitativo Multi-Lente (Hito 2) — KineTopus-Analyst.

Por defecto ejecuta el motor Multi-Lente (`2000v` Fondo / `1000v` Confirmación / `500v` Timing)
sobre una única descarga (`10y`, con respaldo automático a `max`), exportando siempre el rastro
completo para lectura escalonada:
  1. `confluence.json` + `confluence.png` (síntesis jerárquica e imagen ejecutiva principal).
  2. `lens_<W>/telemetry.json` + `lens_<W>/dashboard.png` (6 paneles con anotaciones y Zoom Táctico).
  3. `lens_<W>/panels/01..06.png` (paneles individuales en alta resolución `dpi=200`).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
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
        description="Ejecuta un análisis físico-predictivo Multi-Lente estandarizado con KineTopus-Analyst."
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
        help="Tres ventanas jerárquicas separadas por coma (default: 2000,1000,500).",
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
    parser.add_argument("--wf-cuts", type=int, default=10, help="Cortes objetivo para el Walk-Forward estricto (default: 10).")
    parser.add_argument("--min-wf-cuts", type=int, default=5, help="Mínimo de cortes efectivos OOS para aprobar sello (default: 5).")
    parser.add_argument("--no-max-fallback", action="store_true", help="Desactiva la ampliación automática de '10y' a 'max'.")
    parser.add_argument("--no-parallel", action="store_true", help="Ejecuta las 3 lentes de forma secuencial en lugar de paralela.")
    parser.add_argument("--no-auto-tune", action="store_true", help="Desactiva la calibración automática CUSUMAutoTuner.")
    parser.add_argument("--no-auto-rescue", action="store_true", help="Desactiva el rescate automático Autopilot 2D.")
    parser.add_argument("--classic-price", action="store_true", help="Modo Física Clásica: usa P(t) directo en lugar de retornos logarítmicos.")
    parser.add_argument("--disable-norm", action="store_true", help="Desactiva normalización Z-Score (sistemas sintéticos ideales).")
    parser.add_argument("--csv", type=str, default=None, help="Ruta opcional a un archivo CSV local en vez de Yahoo Finance.")
    parser.add_argument("--output-dir", type=str, default=None, help="Directorio de salida (default: reports/<TICKER>/<TIMESTAMP>/).")
    return parser.parse_args()


def _run_single_lens_mode(args: argparse.Namespace, ticker_label: str, df_override: Any, out_dir: Path) -> int:
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
        "directional_inertia": kpis["directional_inertia"],
        "sindy_r2": kpis["sindy_r2_score"],
        "cusum_status": kpis["cusum_semaphore"],
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
        wf_cuts=args.wf_cuts,
        min_wf_effective_cuts=args.min_wf_cuts,
        parallel=not args.no_parallel,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    runner = KinetopusMultiLensRunner(m_cfg)
    multi_res = runner.run(df_override=df_override)

    conf_png_path = out_dir / "confluence.png"
    conf_json_path = out_dir / "confluence.json"
    KinetopusStaticRenderer.render_confluence_chart(multi_res, str(conf_png_path))

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

    multi_res.confluence["artifacts"] = {
        "report_dir": str(out_dir),
        "confluence_json": str(conf_json_path),
        "confluence_png": str(conf_png_path),
        "expected_analysis_md": str(out_dir / "analysis.md"),
        "lenses": lens_artifacts,
    }

    with open(conf_json_path, "w", encoding="utf-8") as f:
        json.dump(multi_res.confluence, f, indent=2, ensure_ascii=False)

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
        "confluence_png": str(conf_png_path),
        "telemetry_json": str(conf_json_path),
        "dashboard_png": str(conf_png_path),
        "lenses": lens_artifacts,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
