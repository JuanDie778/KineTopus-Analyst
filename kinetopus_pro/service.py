"""
Micro-Servicio HTTP REST (`FastAPI`) + Portal Web Ligero (`v0.4.0` — Hito 4).

Expone el motor Multi-Lente KineTopus como servicio local o B2B mediante:
  - `GET  /`                          -> Portal Web Ligero (Oscuro/Claro, lanzador y vista previa iframe)
  - `GET  /api/v1/health`             -> Estado del servicio, versión y gancho para Hito 3
  - `GET  /api/v1/tickers`            -> Catálogo de activos analizados en caché + URLs directas
  - `POST /api/v1/analyze`            -> Ejecuta o carga un activo (`ticker` o `csv_content`) bajo Lock RAM
  - `GET  /api/v1/indicator/{ticker}` -> Contrato ligero B2B `indicator_feed.json` (`~5-12 KB`)
  - `GET  /api/v1/pine/{ticker}`      -> Código TradingView Pine Script v5 (`text/plain`)
  - `GET  /api/v1/alerts`             -> Todas las alertas activas del catálogo (`?only_new=false`)
  - `GET  /api/v1/alerts/{ticker}`    -> Alertas activas de un activo (`?only_new=false`)
  - `GET  /reports/{ticker}/widget`   -> Widget SVG `< 35 KB` embebible en `<iframe>` (`?theme=dark|light`)
  - `GET  /reports/{ticker}/latest`   -> Reporte completo interactivo `report.html`
"""

import argparse
import io
import json
import shutil
import threading
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import jinja2
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from kinetopus_pro.alerts import KinetopusAlertEngine
from kinetopus_pro.cli import sanitize_ticker_folder
from kinetopus_pro.indicator_export import KinetopusIndicatorExporter
from kinetopus_pro.multi_lens import DEFAULT_MULTI_LENSES, KinetopusMultiLensRunner, MultiLensConfig
from kinetopus_pro.report_builder import KinetopusReportBuilder
from kinetopus_pro.static_renderer import KinetopusStaticRenderer

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE_VERSION = "0.4.0"
_GLOBAL_ANALYZE_LOCK = threading.Lock()


class AnalyzeRequest(BaseModel):
    """Cuerpo JSON para lanzar o refrescar un análisis Multi-Lente vía HTTP."""

    ticker: str = Field(default="BTC-USD", description="Símbolo del activo o identificador de la serie.")
    csv_content: Optional[str] = Field(
        default=None,
        description="Contenido CSV opcional en texto plano (columnas Date/Close o OHLCV) para modo offline/custom.",
    )
    interval: str = Field(default="1d", description="Intervalo temporal: 1h, 1d, 1wk, 1mo.")
    period: str = Field(default="10y", description="Periodo base Yahoo Finance: 1y..10y, max.")
    lenses: List[int] = Field(default=[2000, 1000, 500], description="Tres ventanas jerárquicas [Contexto, Principal, Sensor].")
    horizon: int = Field(default=150, ge=10, le=500, description="Horizonte proyectado t+N en velas.")
    smooth_tol: float = Field(default=0.0050, gt=0.0, description="Tolerancia inicial del Spline C².")
    cusum_k: Optional[float] = Field(default=None, description="Drift CUSUM manual opcional.")
    cusum_h: float = Field(default=5.0, gt=0.5, description="Umbral estructural H de quiebre CUSUM.")
    audit_oos: bool = Field(default=False, description="Activa auditoría histórica Walk-Forward OOS.")
    classic_price: bool = Field(default=False, description="Usa P(t) directo en vez de retornos logarítmicos.")
    disable_norm: bool = Field(default=False, description="Desactiva normalización Z-Score.")
    auto_tune: bool = Field(default=True, description="Activa calibración automática CUSUMAutoTuner.")
    auto_rescue: bool = Field(default=True, description="Activa rescate automático Autopilot 2D.")
    parallel: bool = Field(default=False, description="Ejecuta las 3 lentes en paralelo (default False en servidor para ahorrar RAM).")
    refresh: bool = Field(default=False, description="Fuerza recálculo aunque exista corrida reciente en caché.")
    webhook_url: Optional[str] = Field(default=None, description="URL opcional para despacho HTTP POST de alertas nuevas.")


class KinetopusReportStore:
    """Gestor de almacenamiento, caché en disco y ejecución protegida para API y MCP."""

    TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

    def __init__(self, reports_root: Optional[Path] = None):
        default_root = (REPO_ROOT / "reports") if (REPO_ROOT / "pyproject.toml").is_file() else (Path.cwd() / "reports")
        self.reports_root = Path(reports_root).resolve() if reports_root is not None else default_root.resolve()
        self.reports_root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.reports_root / ".alerts_ledger.json"

    def _resolve_ticker_folder(self, ticker: str) -> Optional[Path]:
        safe = sanitize_ticker_folder(ticker)
        direct = self.reports_root / safe
        if direct.is_dir():
            return direct
        lower_target = safe.lower()
        for child in self.reports_root.iterdir():
            if child.is_dir() and not child.name.startswith(".") and child.name.lower() == lower_target:
                return child
        return None

    def find_latest_run_dir(self, ticker: str, interval: Optional[str] = None) -> Optional[Path]:
        """Devuelve la carpeta más reciente con `confluence.json` válido para `ticker`."""
        t_dir = self._resolve_ticker_folder(ticker)
        if t_dir is None or not t_dir.is_dir():
            return None

        candidates = sorted(
            [d for d in t_dir.iterdir() if d.is_dir() and (d / "confluence.json").is_file()],
            key=lambda p: p.name,
            reverse=True,
        )
        if not candidates:
            return None

        if interval is None:
            return candidates[0]

        for cand in candidates:
            try:
                with open(cand / "confluence.json", "r", encoding="utf-8") as f:
                    conf = json.load(f)
                c_int = conf.get("metadata", {}).get("dataset", {}).get("interval")
                if c_int == interval:
                    return cand
            except Exception:
                continue
        return candidates[0]

    def ensure_portable_artifacts(
        self,
        report_dir: Path,
        webhook_url: Optional[str] = None,
        force_rebuild: bool = False,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Garantiza que `alerts.json`, `indicator_feed.json`, `indicator.pine` y `widget.html` existan."""
        rep = Path(report_dir).resolve()
        alerts_path = rep / "alerts.json"
        feed_path = rep / "indicator_feed.json"
        pine_path = rep / "indicator.pine"
        widget_path = rep / "widget.html"

        if force_rebuild or webhook_url or not alerts_path.is_file():
            alerts_payload = KinetopusAlertEngine.evaluate_directory(
                report_dir=rep,
                ledger_path=self.ledger_path,
                webhook_url=webhook_url,
            )
        else:
            with open(alerts_path, "r", encoding="utf-8") as f:
                alerts_payload = json.load(f)

        if force_rebuild or not (feed_path.is_file() and pine_path.is_file() and widget_path.is_file()):
            KinetopusIndicatorExporter.export_from_directory(
                report_dir=rep,
                alerts_payload=alerts_payload,
            )

        with open(feed_path, "r", encoding="utf-8") as f:
            feed_payload = json.load(f)
        return feed_payload, alerts_payload

    @staticmethod
    def _build_urls_for_ticker(ticker: str) -> Dict[str, str]:
        enc = urllib.parse.quote(ticker, safe="")
        return {
            "indicator_json": f"/api/v1/indicator/{enc}",
            "pine_script": f"/api/v1/pine/{enc}",
            "alerts_json": f"/api/v1/alerts/{enc}",
            "widget_html": f"/reports/{enc}/widget",
            "report_html": f"/reports/{enc}/latest",
        }

    def summarize_run_dir(self, report_dir: Path) -> Dict[str, Any]:
        feed, alerts = self.ensure_portable_artifacts(report_dir)
        asset = feed["asset"]
        verdict = feed["verdict"]
        ticker = asset["ticker"]
        pri = next(
            (l for l in feed.get("lenses", []) if l.get("role_code") == "PRINCIPAL_PREDICTIVA"),
            feed["lenses"][0] if feed.get("lenses") else {},
        )
        return {
            "ticker": ticker,
            "folder_name": report_dir.parent.name,
            "latest_run": report_dir.name,
            "report_dir": str(report_dir),
            "interval": asset["interval"],
            "last_date": asset["last_date"],
            "last_close_price": asset["last_close_price"],
            "human_banner": verdict["human_banner"],
            "global_physical_confidence": verdict["global_physical_confidence"],
            "primary_curve_r2": pri.get("curve_price_r2"),
            "primary_t150_return_pct": pri.get("t150_return_pct"),
            "active_alerts_count": alerts.get("total_active_alerts", 0),
            "new_alerts_count": alerts.get("new_alerts_count", 0),
            "highest_alert_severity": alerts.get("highest_severity", "NONE"),
            "has_full_report": (report_dir / "report.html").is_file(),
            "urls": self._build_urls_for_ticker(ticker),
        }

    def list_cached_tickers(self) -> List[Dict[str, Any]]:
        if not self.reports_root.is_dir():
            return []
        items: List[Dict[str, Any]] = []
        for child in sorted(self.reports_root.iterdir(), key=lambda p: p.name):
            if not child.is_dir() or child.name.startswith("."):
                continue
            latest = self.find_latest_run_dir(child.name)
            if latest is None:
                continue
            try:
                items.append(self.summarize_run_dir(latest))
            except Exception:
                continue
        return items

    def collect_all_alerts(self, only_new: bool = False) -> Dict[str, Any]:
        combined: List[Dict[str, Any]] = []
        tickers_checked = 0
        for child in sorted(self.reports_root.iterdir(), key=lambda p: p.name):
            if not child.is_dir() or child.name.startswith("."):
                continue
            latest = self.find_latest_run_dir(child.name)
            if latest is None:
                continue
            try:
                _, alerts_obj = self.ensure_portable_artifacts(latest)
                tickers_checked += 1
                for al in alerts_obj.get("alerts", []):
                    if not only_new or bool(al.get("is_new")):
                        combined.append(al)
            except Exception:
                continue

        sev_rank = {"CRITICAL": 3, "WARNING": 2, "INFO": 1}
        combined.sort(key=lambda a: (sev_rank.get(a.get("severity", ""), 0), a.get("last_date", "")), reverse=True)
        return {
            "schema_version": KinetopusAlertEngine.SCHEMA_VERSION,
            "tickers_checked": tickers_checked,
            "only_new_filter": bool(only_new),
            "total_alerts": len(combined),
            "alerts": combined,
        }

    def run_or_load_analysis(
        self,
        ticker: str,
        csv_content: Optional[str] = None,
        interval: str = "1d",
        period: str = "10y",
        lenses: Sequence[int] = DEFAULT_MULTI_LENSES,
        horizon: int = 150,
        smooth_tol: float = 0.0050,
        cusum_k: Optional[float] = None,
        cusum_h: float = 5.0,
        audit_oos: bool = False,
        classic_price: bool = False,
        disable_norm: bool = False,
        auto_tune: bool = True,
        auto_rescue: bool = True,
        parallel: bool = False,
        refresh: bool = False,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Carga desde caché si existe (`refresh=False`), o ejecuta el pipeline completo bajo Lock RAM."""
        clean_ticker = ticker.strip() or "CUSTOM_ASSET"
        if not refresh and csv_content is None:
            existing = self.find_latest_run_dir(clean_ticker, interval=interval)
            if existing is not None:
                summary = self.summarize_run_dir(existing)
                summary["cached"] = True
                return summary

        sorted_lenses = tuple(sorted((int(w) for w in lenses), reverse=True))
        if len(sorted_lenses) != 3 or any(w <= 20 for w in sorted_lenses):
            raise ValueError("`lenses` debe contener exactamente 3 ventanas mayores a 20 velas (ej. [2000, 1000, 500]).")

        df_override = None
        if csv_content is not None:
            df_override = pd.read_csv(io.StringIO(csv_content))

        with _GLOBAL_ANALYZE_LOCK:
            ts_str = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")[:19]
            safe_folder = sanitize_ticker_folder(clean_ticker)
            out_dir = self.reports_root / safe_folder / ts_str
            out_dir.mkdir(parents=True, exist_ok=True)

            m_cfg = MultiLensConfig(
                ticker=clean_ticker,
                base_period=period,
                fallback_period="max",
                interval=interval,
                lenses=sorted_lenses,
                horizon_steps=int(horizon),
                smooth_tol=float(smooth_tol),
                cusum_k=cusum_k,
                cusum_h=float(cusum_h),
                poly_degree=1,
                disable_norm=bool(disable_norm),
                disable_returns=bool(classic_price),
                auto_tune=bool(auto_tune),
                auto_rescue=bool(auto_rescue),
                audit_oos=bool(audit_oos),
                wf_cuts=10 if audit_oos else 0,
                parallel=bool(parallel),
            )
            multi_res = KinetopusMultiLensRunner(m_cfg).run(df_override=df_override)

            hero_png_path = out_dir / "hero.png"
            conf_png_path = out_dir / "confluence.png"
            conf_json_path = out_dir / "confluence.json"

            KinetopusStaticRenderer.render_hero_chart(multi_res, str(hero_png_path))
            shutil.copy2(hero_png_path, conf_png_path)

            lens_artifacts: Dict[str, Any] = {}
            for slot in multi_res.lens_slots:
                w_key = str(slot.window_candles)
                if not slot.available or slot.run_result is None:
                    lens_artifacts[w_key] = {"status": "N/D", "reason": slot.unavailable_reason}
                    continue
                lens_dir = out_dir / f"lens_{slot.window_candles}"
                lens_dir.mkdir(parents=True, exist_ok=True)
                l_json = lens_dir / "telemetry.json"
                l_dash = lens_dir / "dashboard.png"
                dash_abs = KinetopusStaticRenderer.render_dashboard(slot.run_result, str(l_dash))
                with open(l_json, "w", encoding="utf-8") as f:
                    json.dump(slot.run_result.telemetry, f, indent=2, ensure_ascii=False)
                lens_artifacts[w_key] = {
                    "status": "OK",
                    "lens_dir": str(lens_dir),
                    "telemetry_json": str(l_json),
                    "dashboard_png": dash_abs,
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
                "indicator_feed_json": str(out_dir / "indicator_feed.json"),
                "widget_html": str(out_dir / "widget.html"),
                "indicator_pine": str(out_dir / "indicator.pine"),
                "alerts_json": str(out_dir / "alerts.json"),
                "lenses": lens_artifacts,
            }
            with open(conf_json_path, "w", encoding="utf-8") as f:
                json.dump(multi_res.confluence, f, indent=2, ensure_ascii=False)

            KinetopusReportBuilder.render_from_directory(report_dir=out_dir)
            self.ensure_portable_artifacts(out_dir, webhook_url=webhook_url, force_rebuild=True)

        summary = self.summarize_run_dir(out_dir)
        summary["cached"] = False
        return summary


def create_app(reports_root: Optional[Path] = None) -> FastAPI:
    """Construye la aplicación FastAPI lista para `uvicorn` o `TestClient`."""
    store = KinetopusReportStore(reports_root=reports_root)
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(store.TEMPLATE_DIR)),
        autoescape=jinja2.select_autoescape(["html", "xml"]),
    )

    app = FastAPI(
        title="KineTopus-Analyst B2B & Portable Indicator API",
        version=SERVICE_VERSION,
        description=(
            "Servicio cuantitativo Multi-Lente (2000v Cian / 1000v Ámbar / 500v Violeta), "
            "feeds B2B JSON, widgets SVG <35 KB, overlays Pine Script v5 y alertas deduplicadas."
        ),
    )
    app.state.store = store

    @app.get("/", response_class=HTMLResponse)
    def get_portal() -> HTMLResponse:
        tickers = store.list_cached_tickers()
        alerts_all = store.collect_all_alerts(only_new=False)["alerts"]
        tpl = env.get_template("portal.html.j2")
        html = tpl.render(
            version=SERVICE_VERSION,
            reports_root=str(store.reports_root),
            tickers=tickers,
            active_alerts=alerts_all,
        )
        return HTMLResponse(content=html)

    @app.get("/api/v1/health")
    def get_health() -> Dict[str, Any]:
        tickers = store.list_cached_tickers()
        return {
            "status": "ok",
            "version": SERVICE_VERSION,
            "reports_root": str(store.reports_root),
            "cached_tickers_count": len(tickers),
            "hito3_scanner_attached": False,
        }

    @app.get("/api/v1/tickers")
    def get_tickers() -> Dict[str, Any]:
        tickers = store.list_cached_tickers()
        return {
            "count": len(tickers),
            "tickers": tickers,
        }

    @app.post("/api/v1/analyze")
    def post_analyze(req: AnalyzeRequest) -> Dict[str, Any]:
        try:
            result = store.run_or_load_analysis(
                ticker=req.ticker,
                csv_content=req.csv_content,
                interval=req.interval,
                period=req.period,
                lenses=req.lenses,
                horizon=req.horizon,
                smooth_tol=req.smooth_tol,
                cusum_k=req.cusum_k,
                cusum_h=req.cusum_h,
                audit_oos=req.audit_oos,
                classic_price=req.classic_price,
                disable_norm=req.disable_norm,
                auto_tune=req.auto_tune,
                auto_rescue=req.auto_rescue,
                parallel=req.parallel,
                refresh=req.refresh,
                webhook_url=req.webhook_url,
            )
            return {"status": "ok", **result}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Fallo en motor KineTopus: {exc}") from exc

    @app.get("/api/v1/indicator/{ticker}")
    def get_indicator(
        ticker: str,
        include_series: bool = Query(default=True),
        refresh: bool = Query(default=False),
    ) -> Dict[str, Any]:
        if refresh:
            store.run_or_load_analysis(ticker=ticker, refresh=True)
        rep = store.find_latest_run_dir(ticker)
        if rep is None:
            raise HTTPException(
                status_code=404,
                detail=f"No existe corrida en caché para '{ticker}'. Invoca primero POST /api/v1/analyze.",
            )
        feed, _ = store.ensure_portable_artifacts(rep)
        if not include_series:
            feed = {k: v for k, v in feed.items() if k != "series"}
        return feed

    @app.get("/api/v1/pine/{ticker}", response_class=PlainTextResponse)
    def get_pine(ticker: str) -> PlainTextResponse:
        rep = store.find_latest_run_dir(ticker)
        if rep is None:
            raise HTTPException(status_code=404, detail=f"No existe corrida en caché para '{ticker}'.")
        store.ensure_portable_artifacts(rep)
        pine_text = (rep / "indicator.pine").read_text(encoding="utf-8")
        return PlainTextResponse(content=pine_text)

    @app.get("/api/v1/alerts")
    def get_all_alerts(only_new: bool = Query(default=False)) -> Dict[str, Any]:
        return store.collect_all_alerts(only_new=only_new)

    @app.get("/api/v1/alerts/{ticker}")
    def get_ticker_alerts(ticker: str, only_new: bool = Query(default=False)) -> Dict[str, Any]:
        rep = store.find_latest_run_dir(ticker)
        if rep is None:
            raise HTTPException(status_code=404, detail=f"No existe corrida en caché para '{ticker}'.")
        _, alerts_obj = store.ensure_portable_artifacts(rep)
        if only_new:
            filtered = [a for a in alerts_obj.get("alerts", []) if bool(a.get("is_new"))]
            alerts_obj = dict(alerts_obj)
            alerts_obj["alerts"] = filtered
            alerts_obj["only_new_filter"] = True
        return alerts_obj

    @app.get("/reports/{ticker}/widget", response_class=HTMLResponse)
    def get_ticker_widget(
        ticker: str,
        theme: str = Query(default="dark"),
    ) -> HTMLResponse:
        rep = store.find_latest_run_dir(ticker)
        if rep is None:
            raise HTTPException(status_code=404, detail=f"No existe corrida en caché para '{ticker}'.")
        feed, alerts_obj = store.ensure_portable_artifacts(rep)
        if str(theme).lower() in ("light", "dark") and str(theme).lower() != "dark":
            html = KinetopusIndicatorExporter.render_embed_widget(
                feed=feed, alerts_payload=alerts_obj, default_theme="light"
            )
        else:
            html = (rep / "widget.html").read_text(encoding="utf-8")
        return HTMLResponse(content=html)

    @app.get("/reports/{ticker}/latest", response_class=HTMLResponse)
    def get_latest_report(ticker: str) -> HTMLResponse:
        rep = store.find_latest_run_dir(ticker)
        if rep is None:
            raise HTTPException(status_code=404, detail=f"No existe corrida en caché para '{ticker}'.")
        report_html_path = rep / "report.html"
        if not report_html_path.is_file():
            if (rep / "report_bundle.npz").is_file():
                KinetopusReportBuilder.render_from_directory(report_dir=rep)
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"La corrida '{rep.name}' no incluye report.html ni report_bundle.npz.",
                )
        return HTMLResponse(content=report_html_path.read_text(encoding="utf-8"))

    return app


def parse_serve_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inicia el servidor HTTP B2B y Portal Web Ligero de KineTopus-Analyst (v0.4.0)."
    )
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host de escucha (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="Puerto HTTP (default: 8000).")
    parser.add_argument(
        "--reports-dir",
        type=str,
        default=None,
        help="Directorio raíz de corridas `reports/` (por defecto `<REPO_ROOT>/reports`).",
    )
    return parser.parse_args()


def main() -> int:
    import uvicorn

    args = parse_serve_args()
    rep_root = Path(args.reports_dir).resolve() if args.reports_dir else None
    app = create_app(reports_root=rep_root)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
