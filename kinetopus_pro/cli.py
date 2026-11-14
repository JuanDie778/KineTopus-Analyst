#!/usr/bin/env python3
"""
CLI Estandarizado de Análisis Cuantitativo — KineTopus-Pro.

Ejecuta el motor Headless completo sobre un activo de Yahoo Finance o CSV local,
exportando obligatoriamente el doble canal auditable:
  1. `telemetry.json`: Telemetría matemática, cinemática, Sello de Fiabilidad y calendario CUSUM.
  2. `dashboard.png` : Dashboard visual de 5 paneles (`Matplotlib Agg`).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

# Silenciar warnings verbosos de esparsidad de PySINDy durante el barrido STLSQ
warnings.filterwarnings("ignore", category=UserWarning)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent

from kinetopus_pro.headless_pipeline import KinetopusAnalysisConfig, KinetopusHeadlessPipeline
from kinetopus_pro.static_renderer import KinetopusStaticRenderer


def sanitize_ticker_folder(raw_name: str) -> str:
    """Convierte símbolos con caracteres especiales (ej. GC=F, ^GSPC, BTC-USD) en carpetas seguras."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name.strip())
    return cleaned.strip("_") or "CUSTOM_ASSET"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta un análisis físico-predictivo estandarizado con KineTopus-Pro."
    )
    parser.add_argument("--ticker", type=str, default="BTC-USD", help="Símbolo en Yahoo Finance (default: BTC-USD).")
    parser.add_argument("--period", type=str, default="5y", help="Periodo histórico: 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max (default: 5y).")
    parser.add_argument("--interval", type=str, default="1d", help="Resolución de vela: 1h, 1d, 1wk, 1mo (default: 1d).")
    parser.add_argument("--context-window", type=int, default=1000, help="Ventana activa de velas para Spline/CUSUM (default: 1000, 0=todo).")
    parser.add_argument("--horizon", type=int, default=150, help="Horizonte predictivo t+N en velas (default: 150).")
    parser.add_argument("--smooth-tol", type=float, default=0.0050, help="Tolerancia inicial del Spline C² (default: 0.0050).")
    parser.add_argument("--cusum-k", type=float, default=None, help="Drift CUSUM manual (si se omite, CUSUMAutoTuner lo calibra automáticamente).")
    parser.add_argument("--cusum-h", type=float, default=5.0, help="Umbral crítico H de quiebre CUSUM (default: 5.0).")
    parser.add_argument("--poly-degree", type=int, default=1, choices=[1, 2, 3], help="Grado polinomial SINDy (default: 1).")
    parser.add_argument("--wf-cuts", type=int, default=10, help="Número de cortes OOS para el Mini Walk-Forward de fiabilidad (default: 10).")
    parser.add_argument("--no-auto-tune", action="store_true", help="Desactiva la calibración automática CUSUMAutoTuner.")
    parser.add_argument("--no-auto-rescue", action="store_true", help="Desactiva el rescate automático Autopilot 2D.")
    parser.add_argument("--classic-price", action="store_true", help="Modo Física Clásica: usa P(t) directo en lugar de retornos logarítmicos.")
    parser.add_argument("--disable-norm", action="store_true", help="Desactiva normalización Z-Score (para sistemas físicos ideales/sintéticos).")
    parser.add_argument("--csv", type=str, default=None, help="Ruta opcional a un archivo CSV local en vez de descargar desde Yahoo Finance.")
    parser.add_argument("--output-dir", type=str, default=None, help="Directorio exacto de salida (por defecto: reports/<TICKER>/<TIMESTAMP>/).")
    return parser.parse_args()


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
    )

    if args.output_dir:
        out_dir = Path(args.output_dir).resolve()
    else:
        ts_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_ticker = sanitize_ticker_folder(ticker_label)
        base_root = REPO_ROOT if (REPO_ROOT / "pyproject.toml").is_file() else Path.cwd()
        out_dir = base_root / "reports" / safe_ticker / ts_str

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "telemetry.json"
    png_path = out_dir / "dashboard.png"

    pipeline = KinetopusHeadlessPipeline(cfg)
    result = pipeline.run(df_override=df_override)

    # Registrar rutas generadas dentro del propio JSON para trazabilidad cruzada
    result.telemetry["artifacts"] = {
        "report_dir": str(out_dir),
        "telemetry_json": str(json_path),
        "dashboard_png": str(png_path),
        "expected_analysis_md": str(out_dir / "analysis.md"),
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result.telemetry, f, indent=2, ensure_ascii=False)

    KinetopusStaticRenderer.render_dashboard(result, str(png_path))

    kpis = result.telemetry["executive_kpis"]
    ds = result.telemetry["metadata"]["dataset"]
    cal = result.telemetry["calibration"]
    wf = result.telemetry["reliability_seal"]["mini_walk_forward_oos"]
    eqs = result.telemetry["white_box_physics"]["active_equations"]

    summary = {
        "status": "OK",
        "ticker": ds["ticker"],
        "last_date": ds["last_candle_date"],
        "last_close": ds["last_close_price"],
        "calibrated_k": cal["effective_cusum_k"],
        "effective_tol": cal["effective_smooth_tol"],
        "autopilot_rescued": cal["autopilot_rescue"]["applied"],
        "directional_inertia": kpis["directional_inertia"],
        "sindy_r2": kpis["sindy_r2_score"],
        "cusum_status": kpis["cusum_semaphore"],
        "oos_physics_class": wf.get("asset_physics_class"),
        "oos_consensus_hr_pct": wf.get("consensus_hit_ratio_pct"),
        "overall_confidence": kpis["overall_physical_confidence"],
        "active_equations": eqs,
        "report_dir": str(out_dir),
        "telemetry_json": str(json_path),
        "dashboard_png": str(png_path),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
