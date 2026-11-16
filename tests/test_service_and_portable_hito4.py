"""
Suite de Auditoría Hito 4 (`v0.4.0`) — Servicio HTTP/MCP, Indicador Portable B2B y Alertas Activas.

Verifica de forma 100% offline y determinista:
  1. Contrato y ligereza de `indicator_feed.json` (`kinetopus.indicator.v1`, `< 25 KB`), paridad
     exacta con `confluence.json` y retrocompatibilidad con corridas estilo `v0.3.0`.
  2. Widget embebible `widget.html` (`< 35 KB`, SVG puro sin `plotly.min.js`, Oscuro/Claro, cero
     enums crudos `Q1..Q4`) y overlay TradingView Pine Script v5 (`indicator.pine`).
  3. Motor de Alertas (`KinetopusAlertEngine`) + deduplicación (`AlertLedger`, idempotencia en
     mismo `run_key` vs `is_new=False` en re-lectura) + despacho Webhook simulado (`monkeypatch`).
  4. Subcomando CLI ultrarrápido `--export-portable <REPORT_DIR>`.
  5. Endpoints REST `FastAPI` (`TestClient`): `/`, `/api/v1/health`, `/api/v1/tickers`,
     `POST /api/v1/analyze` (con `csv_content` + caché), `/api/v1/indicator/{ticker}`,
     `/api/v1/pine/{ticker}`, `/api/v1/alerts`, `/reports/{ticker}/widget` y `/reports/{ticker}/latest`.
  6. Herramientas nativas MCP (`mcp_server.py`): `list_analyzed_assets`, `get_asset_indicator`,
     `get_asset_alerts` y `get_tradingview_pine`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kinetopus_pro.alerts import AlertLedger, KinetopusAlertEngine
from kinetopus_pro.indicator_export import KinetopusIndicatorExporter
from kinetopus_pro.mcp_server import (
    get_asset_alerts,
    get_asset_indicator,
    get_tradingview_pine,
    list_analyzed_assets,
)
from kinetopus_pro.multi_lens import KinetopusMultiLensRunner, MultiLensConfig
from kinetopus_pro.report_builder import KinetopusReportBuilder
from kinetopus_pro.service import create_app
from kinetopus_pro.static_renderer import KinetopusStaticRenderer


def _make_synthetic_ohlcv(n: int = 420, seed: int = 404) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n)
    t = np.linspace(0.0, 8.0 * np.pi, n, dtype=np.float64)
    r = 0.0010 + 0.0055 * np.sin(t * 0.5) + rng.normal(0.0, 0.0020, n)
    close = 120.0 * np.exp(np.cumsum(r))
    open_p = np.roll(close, 1)
    open_p[0] = close[0] * 0.997
    span = close * 0.006
    high = np.maximum(open_p, close) + span
    low = np.minimum(open_p, close) - span
    vol = 1.8e6 * (1.0 + 0.30 * np.cos(t * 0.5) + rng.uniform(0.05, 0.15, n))
    return pd.DataFrame(
        {"Date": dates.strftime("%Y-%m-%d"), "Open": open_p, "High": high, "Low": low, "Close": close, "Volume": vol}
    )


@pytest.fixture(scope="module")
def sample_report_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Genera una corrida sintética Multi-Lente completa en un directorio temporal compartido."""
    root = tmp_path_factory.mktemp("hito4_reports")
    rep_dir = root / "SYNTH-H4" / "2026-11-15_120000"
    rep_dir.mkdir(parents=True, exist_ok=True)

    df = _make_synthetic_ohlcv(n=420, seed=404).set_index("Date")
    df.index = pd.to_datetime(df.index)

    cfg = MultiLensConfig(
        ticker="SYNTH-H4",
        lenses=(320, 180, 90),
        horizon_steps=60,
        auto_tune=False,
        cusum_k=1.15,
        audit_oos=False,
        parallel=False,
    )
    multi_res = KinetopusMultiLensRunner(cfg).run(df_override=df)

    KinetopusStaticRenderer.render_hero_chart(multi_res, str(rep_dir / "hero.png"))
    for slot in multi_res.lens_slots:
        if slot.available and slot.run_result is not None:
            ldir = rep_dir / f"lens_{slot.window_candles}"
            ldir.mkdir(parents=True, exist_ok=True)
            KinetopusStaticRenderer.render_dashboard(slot.run_result, str(ldir / "dashboard.png"))
            with open(ldir / "telemetry.json", "w", encoding="utf-8") as f:
                json.dump(slot.run_result.telemetry, f, indent=2, ensure_ascii=False)

    KinetopusReportBuilder.save_report_bundle(multi_res, rep_dir)
    KinetopusReportBuilder.write_narrative_template(rep_dir, multi_res.confluence)
    with open(rep_dir / "confluence.json", "w", encoding="utf-8") as f:
        json.dump(multi_res.confluence, f, indent=2, ensure_ascii=False)

    KinetopusReportBuilder.render_from_directory(rep_dir)
    return root


def test_indicator_feed_contract_parity_and_v30_fallback(sample_report_root: Path, tmp_path: Path):
    rep_dir = sample_report_root / "SYNTH-H4" / "2026-11-15_120000"
    feed_path = rep_dir / "indicator_feed.json"
    assert feed_path.is_file()
    assert feed_path.stat().st_size < 25 * 1024

    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    conf = json.loads((rep_dir / "confluence.json").read_text(encoding="utf-8"))

    assert feed["schema_version"] == "kinetopus.indicator.v1"
    assert feed["asset"]["ticker"] == "SYNTH-H4"
    assert feed["asset"]["last_close_price"] == pytest.approx(
        conf["metadata"]["dataset"]["last_close_price"], rel=1e-5
    )
    assert len(feed["lenses"]) == 3

    for l_feed, l_conf in zip(feed["lenses"], conf["lenses_ordered"]):
        assert l_feed["window_candles"] == l_conf["window_candles"]
        assert l_feed["curve_now_price"] == pytest.approx(l_conf["curve_now_price"], rel=1e-4)
        assert l_feed["t150_center_price"] == pytest.approx(
            l_conf["t150_summary"]["center_price"], rel=1e-4
        )
        # Cero códigos crudos Q1..Q4
        for str_val in (l_feed["state_label"], l_feed["full_label"]):
            assert not any(q in str_val for q in ("Q1_", "Q2_", "Q3_", "Q4_"))

    assert "series" in feed
    assert len(feed["series"]["dates_tail"]) == len(feed["series"]["close_tail"])
    assert len(feed["series"]["projections"]["steps"]) >= 2

    # Probar respaldo limpio estilo v0.3.0 (sin t150_summary ni curve_now_price ni report_bundle.npz)
    legacy_dir = tmp_path / "LEGACY_V30"
    legacy_dir.mkdir(parents=True)
    legacy_conf = json.loads(json.dumps(conf))
    legacy_conf["hierarchy_verdict"].pop("ranges_by_lens", None)
    for l_item in legacy_conf["lenses_ordered"]:
        l_item.pop("t150_summary", None)
        l_item.pop("curve_now_price", None)
    for l_item in legacy_conf["lenses_summary"].values():
        l_item.pop("t150_summary", None)
        l_item.pop("curve_now_price", None)
    (legacy_dir / "confluence.json").write_text(json.dumps(legacy_conf), encoding="utf-8")

    fb_feed = KinetopusIndicatorExporter.build_indicator_feed(legacy_dir, include_series=True)
    assert fb_feed["schema_version"] == "kinetopus.indicator.v1"
    assert all(l["curve_now_price"] is not None for l in fb_feed["lenses"])
    assert all(l["t150_center_price"] is not None for l in fb_feed["lenses"])


def test_embed_widget_svg_lightweight_and_pine_v5_overlay(sample_report_root: Path):
    rep_dir = sample_report_root / "SYNTH-H4" / "2026-11-15_120000"
    widget_path = rep_dir / "widget.html"
    pine_path = rep_dir / "indicator.pine"

    assert widget_path.is_file()
    assert pine_path.is_file()
    assert widget_path.stat().st_size < 35 * 1024

    widget_html = widget_path.read_text(encoding="utf-8")
    assert "<svg" in widget_html
    assert "<polyline" in widget_html
    assert "<path" in widget_html
    assert "plotly" not in widget_html.lower()
    assert 'data-theme="dark"' in widget_html
    assert '[data-theme="light"]' in widget_html
    for raw_enum in ("Q1_", "Q2_", "Q3_", "Q4_"):
        assert raw_enum not in widget_html

    pine_code = pine_path.read_text(encoding="utf-8")
    assert pine_code.startswith("//@version=5")
    assert "indicator(" in pine_code and "overlay=true" in pine_code
    assert "line.new(" in pine_code
    assert "linefill.new(" in pine_code
    assert "table.new(position.top_right" in pine_code
    assert "P75" in pine_code and "P25" in pine_code


def test_alert_engine_rules_ledger_deduplication_and_webhook(
    sample_report_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    src_conf = json.loads(
        (sample_report_root / "SYNTH-H4" / "2026-11-15_120000" / "confluence.json").read_text(encoding="utf-8")
    )

    # Corrida previa con estado IMPULSO_ALCISTA en 1000v
    prev_dir = tmp_path / "reports" / "TEST-ALRT" / "2026-11-14_100000"
    curr_dir = tmp_path / "reports" / "TEST-ALRT" / "2026-11-15_100000"
    prev_dir.mkdir(parents=True)
    curr_dir.mkdir(parents=True)

    prev_conf = json.loads(json.dumps(src_conf))
    prev_conf["metadata"]["dataset"]["ticker"] = "TEST-ALRT"
    prev_conf["lenses_ordered"][1]["human_regime"]["state_code"] = "IMPULSO_ALCISTA"
    prev_conf["lenses_ordered"][1]["human_regime"]["state_label"] = "Impulso alcista"
    (prev_dir / "confluence.json").write_text(json.dumps(prev_conf), encoding="utf-8")

    # Corrida actual forzando tensión crítica, divergencia, sobreextensión y cambio de estado
    curr_conf = json.loads(json.dumps(src_conf))
    curr_conf["metadata"]["dataset"]["ticker"] = "TEST-ALRT"
    curr_conf["metadata"]["dataset"]["last_candle_date"] = "2026-11-15"
    pri = curr_conf["lenses_ordered"][1]
    ctx = curr_conf["lenses_ordered"][0]
    sen = curr_conf["lenses_ordered"][2]

    ctx["raw_direction"] = "ALCISTA"
    pri["raw_direction"] = "BAJISTA"
    pri["cusum_tension_ratio"] = 0.91
    pri["cusum_tension_vs_h"] = "4.55 / 5.0"
    pri["price_vs_spline_gap_pct"] = -11.4
    pri["human_regime"]["state_code"] = "CORRECCION_BAJISTA"
    pri["human_regime"]["state_label"] = "Corrección bajista"
    pri["human_regime"]["position_code"] = "DESCOLGADO"
    sen["raw_direction"] = "ALCISTA"
    sen["t150_summary"]["center_return_pct"] = 25.0
    pri["t150_summary"]["center_return_pct"] = -12.0
    curr_conf["hierarchy_verdict"]["tactical_sensor_detail"]["pins"] = [
        {
            "kind": "VELOCITY_TURN",
            "direction": "UP",
            "candles_ago": 9,
            "date": "2026-11-04",
            "price": 115.25,
            "label": "Giro táctico 500v",
        }
    ]
    (curr_dir / "confluence.json").write_text(json.dumps(curr_conf), encoding="utf-8")

    captured_posts: list[Dict[str, Any]] = []

    class _DummyResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req: urllib.request.Request, timeout: float = 5.0):
        captured_posts.append(
            {
                "url": req.full_url,
                "body": json.loads(req.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        return _DummyResp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    ledger_file = tmp_path / "reports" / ".alerts_ledger.json"
    res1 = KinetopusAlertEngine.evaluate_directory(
        report_dir=curr_dir,
        ledger_path=ledger_file,
        webhook_url="https://hooks.example.test/kinetopus",
    )

    codes = {a["rule_code"] for a in res1["alerts"]}
    assert "CUSUM_CRITICAL_TENSION" in codes
    assert "MULTI_LENS_DIVERGENCE" in codes
    assert "CURVE_EXTREME_STRETCH" in codes
    assert "REGIME_STATE_TRANSITION" in codes
    assert "TACTICAL_500V_PIN" in codes
    assert res1["highest_severity"] == "CRITICAL"
    assert res1["new_alerts_count"] == res1["total_active_alerts"]
    assert len(captured_posts) == 1
    assert captured_posts[0]["body"]["ticker"] == "TEST-ALRT"

    # Idempotencia sobre el mismo run_key (ej. Etapa 2 --render-report en la misma carpeta)
    res_same_dir = KinetopusAlertEngine.evaluate_directory(
        report_dir=curr_dir,
        ledger_path=ledger_file,
    )
    assert res_same_dir["new_alerts_count"] == res1["total_active_alerts"]

    # Deduplicación real en una nueva carpeta con exactamente la misma vela/condiciones -> is_new=False
    next_same_candle_dir = tmp_path / "reports" / "TEST-ALRT" / "2026-11-15_180000"
    next_same_candle_dir.mkdir(parents=True)
    (next_same_candle_dir / "confluence.json").write_text(json.dumps(curr_conf), encoding="utf-8")

    res2 = KinetopusAlertEngine.evaluate_directory(
        report_dir=next_same_candle_dir,
        ledger_path=ledger_file,
        webhook_url="https://hooks.example.test/kinetopus",
    )
    assert res2["new_alerts_count"] == 0
    assert res2["webhook_dispatch"]["sent"] is False
    assert res2["webhook_dispatch"]["reason"] == "no_new_alerts"
    assert len(captured_posts) == 1  # No se re-envió por webhook


def test_cli_export_portable_subcommand(sample_report_root: Path, tmp_path: Path):
    target_dir = tmp_path / "CLI_PORTABLE" / "2026-11-15_120000"
    shutil.copytree(sample_report_root / "SYNTH-H4" / "2026-11-15_120000", target_dir)
    for fname in ("indicator_feed.json", "widget.html", "indicator.pine", "alerts.json"):
        f_p = target_dir / fname
        if f_p.exists():
            f_p.unlink()

    proc = subprocess.run(
        [sys.executable, "-m", "kinetopus_pro.cli", "--export-portable", str(target_dir)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(proc.stdout)
    assert out["status"] == "OK"
    assert out["mode"] == "export_portable_hito4"
    for fname in ("indicator_feed.json", "widget.html", "indicator.pine", "alerts.json"):
        assert (target_dir / fname).is_file()


def test_fastapi_service_endpoints_and_portal(tmp_path: Path):
    srv_root = tmp_path / "srv_reports"
    app = create_app(reports_root=srv_root)
    client = TestClient(app)

    r_health0 = client.get("/api/v1/health")
    assert r_health0.status_code == 200
    assert r_health0.json()["version"] == "0.4.0"
    assert r_health0.json()["cached_tickers_count"] == 0
    assert r_health0.json()["hito3_scanner_attached"] is False

    # Analizar serie sintética vía POST /api/v1/analyze (sin red)
    csv_text = _make_synthetic_ohlcv(n=340, seed=777).to_csv(index=False)
    r_post = client.post(
        "/api/v1/analyze",
        json={
            "ticker": "SYNTH-API",
            "csv_content": csv_text,
            "interval": "1d",
            "lenses": [280, 160, 80],
            "horizon": 45,
            "auto_tune": False,
            "cusum_k": 1.15,
            "parallel": False,
        },
    )
    assert r_post.status_code == 200, r_post.text
    post_data = r_post.json()
    assert post_data["ticker"] == "SYNTH-API"
    assert post_data["cached"] is False

    # Segunda llamada sin csv_content y refresh=False -> lectura instantánea desde caché
    r_cached = client.post("/api/v1/analyze", json={"ticker": "SYNTH-API", "refresh": False})
    assert r_cached.status_code == 200
    assert r_cached.json()["cached"] is True

    # Portal Web Ligero
    r_portal = client.get("/")
    assert r_portal.status_code == 200
    assert "SYNTH-API" in r_portal.text
    assert "<iframe" in r_portal.text

    # Catálogo, Indicador B2B, Pine Script, Alertas, Widget y Reporte completo
    r_tickers = client.get("/api/v1/tickers")
    assert r_tickers.status_code == 200
    assert r_tickers.json()["count"] == 1

    r_ind = client.get("/api/v1/indicator/SYNTH-API?include_series=false")
    assert r_ind.status_code == 200
    ind_json = r_ind.json()
    assert ind_json["schema_version"] == "kinetopus.indicator.v1"
    assert "series" not in ind_json

    r_pine = client.get("/api/v1/pine/SYNTH-API")
    assert r_pine.status_code == 200
    assert r_pine.text.startswith("//@version=5")

    r_alerts = client.get("/api/v1/alerts/SYNTH-API")
    assert r_alerts.status_code == 200
    assert r_alerts.json()["ticker"] == "SYNTH-API"

    r_all_alerts = client.get("/api/v1/alerts")
    assert r_all_alerts.status_code == 200
    assert r_all_alerts.json()["tickers_checked"] == 1

    r_widget_light = client.get("/reports/SYNTH-API/widget?theme=light")
    assert r_widget_light.status_code == 200
    assert 'data-theme="light"' in r_widget_light.text
    assert len(r_widget_light.content) < 35 * 1024

    r_latest = client.get("/reports/SYNTH-API/latest")
    assert r_latest.status_code == 200
    assert "KineTopus · v0.3.1" in r_latest.text

    assert client.get("/api/v1/indicator/NONEXISTENT-999").status_code == 404


def test_mcp_server_tools_direct(sample_report_root: Path):
    rep_str = str(sample_report_root)
    cat = list_analyzed_assets(reports_dir=rep_str)
    assert cat["count"] == 1
    assert cat["tickers"][0]["ticker"] == "SYNTH-H4"

    ind = get_asset_indicator("SYNTH-H4", include_series=False, refresh=False, reports_dir=rep_str)
    assert ind["schema_version"] == "kinetopus.indicator.v1"
    assert "series" not in ind

    al = get_asset_alerts(ticker="SYNTH-H4", reports_dir=rep_str)
    assert al["ticker"] == "SYNTH-H4"

    pine = get_tradingview_pine("SYNTH-H4", reports_dir=rep_str)
    assert pine.startswith("//@version=5")
