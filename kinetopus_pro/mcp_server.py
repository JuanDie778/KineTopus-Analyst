"""
Servidor MCP (`stdio`) de KineTopus-Analyst (`v0.4.0` — Hito 4).

Expone el catálogo cuantitativo Multi-Lente, los feeds B2B `kinetopus.indicator.v1`,
el motor de alertas físico-geométricas y el generador Pine Script v5 como herramientas
nativas para clientes MCP (Claude Desktop, Antigravity, Cursor, agentes B2B).
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from kinetopus_pro.service import KinetopusReportStore

mcp = FastMCP("KineTopus-Analyst")


def _resolve_store(reports_dir: str = "") -> KinetopusReportStore:
    chosen = reports_dir.strip() or os.environ.get("KINETOPUS_REPORTS_DIR", "").strip()
    root_path: Optional[Path] = Path(chosen).resolve() if chosen else None
    return KinetopusReportStore(reports_root=root_path)


@mcp.tool()
def list_analyzed_assets(reports_dir: str = "") -> Dict[str, Any]:
    """Lista los activos analizados en caché con su estado humano 1000v, R², retorno t+150 y alertas."""
    store = _resolve_store(reports_dir)
    tickers = store.list_cached_tickers()
    return {
        "reports_root": str(store.reports_root),
        "count": len(tickers),
        "tickers": tickers,
    }


@mcp.tool()
def get_asset_indicator(
    ticker: str,
    include_series: bool = False,
    refresh: bool = False,
    reports_dir: str = "",
) -> Dict[str, Any]:
    """Devuelve el contrato `kinetopus.indicator.v1` de las 3 lentes (2000v/1000v/500v) y escenarios t+150."""
    store = _resolve_store(reports_dir)
    if refresh or store.find_latest_run_dir(ticker) is None:
        store.run_or_load_analysis(ticker=ticker, refresh=bool(refresh))
    rep = store.find_latest_run_dir(ticker)
    if rep is None:
        raise ValueError(f"No se pudo resolver ni generar corrida para '{ticker}'.")
    feed, _ = store.ensure_portable_artifacts(rep)
    if not include_series:
        feed = {k: v for k, v in feed.items() if k != "series"}
    return feed


@mcp.tool()
def get_asset_alerts(
    ticker: str = "",
    only_new: bool = False,
    reports_dir: str = "",
) -> Dict[str, Any]:
    """Consulta las alertas físico-geométricas activas de un ticker específico o de todo el catálogo."""
    store = _resolve_store(reports_dir)
    if not ticker.strip():
        return store.collect_all_alerts(only_new=only_new)

    rep = store.find_latest_run_dir(ticker)
    if rep is None:
        raise ValueError(f"No existe corrida en caché para '{ticker}'.")
    _, alerts_obj = store.ensure_portable_artifacts(rep)
    if only_new:
        alerts_obj = dict(alerts_obj)
        alerts_obj["alerts"] = [a for a in alerts_obj.get("alerts", []) if bool(a.get("is_new"))]
        alerts_obj["only_new_filter"] = True
    return alerts_obj


@mcp.tool()
def get_tradingview_pine(ticker: str, reports_dir: str = "") -> str:
    """Devuelve el código TradingView Pine Script v5 (`overlay=true`) del activo indicado."""
    store = _resolve_store(reports_dir)
    rep = store.find_latest_run_dir(ticker)
    if rep is None:
        raise ValueError(f"No existe corrida en caché para '{ticker}'.")
    store.ensure_portable_artifacts(rep)
    return (rep / "indicator.pine").read_text(encoding="utf-8")


def main() -> int:
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
