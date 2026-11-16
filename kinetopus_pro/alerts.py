"""
Motor de Alertas Activas, Ledger de Deduplicación y Despacho Webhook (`v0.4.0` — Hito 4).

Evalúa reglas físico-geométricas deterministas sobre `confluence.json` (sin inventar cifras ni
bloquear proyecciones), deduplica eventos mediante huella SHA-256 persistida en `.alerts_ledger.json`
y soporta envío opcional saliente vía HTTP POST JSON (`--webhook-url`).
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SEVERITY_RANK: Dict[str, int] = {
    "CRITICAL": 3,
    "WARNING": 2,
    "INFO": 1,
}


class AlertLedger:
    """Registro ligero en JSON para evitar notificar dos veces la misma condición estructural."""

    def __init__(self, ledger_path: Path):
        self.ledger_path = Path(ledger_path).resolve()
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.ledger_path.is_file():
            self._entries = {}
            return
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and isinstance(raw.get("entries"), dict):
                self._entries = dict(raw["entries"])
            else:
                self._entries = {}
        except Exception:
            self._entries = {}

    def save(self) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "kinetopus.alerts_ledger.v1",
            "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_fingerprints": len(self._entries),
            "entries": self._entries,
        }
        with open(self.ledger_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def mark_and_check_is_new(
        self,
        fingerprint: str,
        ticker: str,
        rule_code: str,
        run_key: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Devuelve `(is_new, first_seen_utc)`.
        Si `run_key` coincide con `first_seen_run` (p. ej. al re-ejecutar Etapa 2 `--render-report`
        sobre el mismo directorio de corrida), preserva `is_new = True` de forma idempotente.
        """
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        existing = self._entries.get(fingerprint)
        if existing is None:
            self._entries[fingerprint] = {
                "ticker": ticker,
                "rule_code": rule_code,
                "first_seen_utc": now_utc,
                "last_seen_utc": now_utc,
                "first_seen_run": run_key or now_utc,
                "seen_count": 1,
            }
            return True, now_utc

        existing["last_seen_utc"] = now_utc
        existing["seen_count"] = int(existing.get("seen_count", 1)) + 1
        first_utc = str(existing.get("first_seen_utc", now_utc))
        if run_key and existing.get("first_seen_run") == run_key:
            return True, first_utc
        return False, first_utc


class KinetopusAlertEngine:
    """Evaluador determinista de alertas multi-lente (`2000v / 1000v / 500v`) y despachador webhook."""

    SCHEMA_VERSION = "kinetopus.alerts.v1"

    @staticmethod
    def compute_fingerprint(ticker: str, interval: str, rule_code: str, anchor_ref: str) -> str:
        raw_key = f"{ticker.upper().strip()}|{interval.strip()}|{rule_code.strip()}|{anchor_ref.strip()}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def resolve_default_ledger_path(report_dir: Path) -> Path:
        rep = Path(report_dir).resolve()
        if rep.parent.parent.name.lower() == "reports":
            return rep.parent.parent / ".alerts_ledger.json"
        if rep.parent.name.lower() == "reports":
            return rep.parent / ".alerts_ledger.json"
        return rep.parent / ".alerts_ledger.json"

    @staticmethod
    def find_previous_confluence(report_dir: Path) -> Optional[Dict[str, Any]]:
        """Busca la corrida inmediatamente anterior del mismo activo en `reports/<TICKER>/`."""
        rep = Path(report_dir).resolve()
        ticker_parent = rep.parent
        if not ticker_parent.is_dir():
            return None

        siblings = sorted(
            [
                d
                for d in ticker_parent.iterdir()
                if d.is_dir() and d.resolve() != rep and (d / "confluence.json").is_file()
            ],
            key=lambda p: p.name,
        )
        if not siblings:
            return None

        older = [d for d in siblings if d.name < rep.name]
        target_dir = older[-1] if older else siblings[-1]
        try:
            with open(target_dir / "confluence.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "lenses_summary" in data:
                return data
        except Exception:
            return None
        return None

    @staticmethod
    def _load_lens_unconsolidated_info(
        report_dir: Optional[Path], window_candles: int
    ) -> Optional[Dict[str, Any]]:
        if report_dir is None:
            return None
        tel_path = Path(report_dir) / f"lens_{window_candles}" / "telemetry.json"
        if not tel_path.is_file():
            return None
        try:
            with open(tel_path, "r", encoding="utf-8") as f:
                tel = json.load(f)
            return tel.get("cusum_forensics", {}).get("unconsolidated_recent_break")
        except Exception:
            return None

    @staticmethod
    def _lens_by_role(confluence: Dict[str, Any], role_code: str) -> Optional[Dict[str, Any]]:
        for item in confluence.get("lenses_ordered", []):
            if item.get("role_code") == role_code:
                return item
        for item in confluence.get("lenses_summary", {}).values():
            if item.get("role_code") == role_code:
                return item
        return None

    @classmethod
    def evaluate_confluence(
        cls,
        confluence: Dict[str, Any],
        previous_confluence: Optional[Dict[str, Any]] = None,
        report_dir: Optional[Path] = None,
        ledger: Optional[AlertLedger] = None,
        run_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evalúa las 6 reglas deterministas sobre `confluence` y devuelve el paquete `alerts.json`."""
        ds = confluence.get("metadata", {}).get("dataset", {})
        hier = confluence.get("hierarchy_verdict", {})
        ticker = str(ds.get("ticker", "UNKNOWN"))
        interval = str(ds.get("interval", "1d"))
        last_date = str(ds.get("last_candle_date", ""))
        last_price = float(ds.get("last_close_price") or 0.0)

        ctx_lens = cls._lens_by_role(confluence, "CONTEXTO_FONDO") or {}
        pri_lens = cls._lens_by_role(confluence, "PRINCIPAL_PREDICTIVA") or {}
        sen_lens = cls._lens_by_role(confluence, "SENSOR_ALERTA") or {}

        raw_alerts: List[Dict[str, Any]] = []

        # ── Regla 1: Tensión CUSUM elevada o crítica en 1000v / 500v ─────────────
        for lens_obj in (pri_lens, sen_lens):
            if not lens_obj.get("available"):
                continue
            win = int(lens_obj["window_candles"])
            t_ratio = float(lens_obj.get("cusum_tension_ratio") or 0.0)
            t_vs_h = str(lens_obj.get("cusum_tension_vs_h", f"{t_ratio * 5.0:.2f} / 5.0"))
            reg_start = str(lens_obj.get("active_regime_start_date", last_date))
            if t_ratio >= 0.85:
                raw_alerts.append(
                    {
                        "rule_code": "CUSUM_CRITICAL_TENSION",
                        "severity": "CRITICAL",
                        "lens_window": win,
                        "title": f"Tensión CUSUM crítica en {win}v ({t_ratio:.0%} del umbral H)",
                        "message": (
                            f"La lente {win}v acumula una tensión CUSUM de {t_vs_h} ({t_ratio:.0%} de H), "
                            "indicando riesgo elevado de cambio estructural de régimen."
                        ),
                        "metrics": {"tension_ratio": round(t_ratio, 3), "tension_vs_h": t_vs_h},
                        "anchor_ref": f"{win}v:crit85:{reg_start}:{last_date}",
                    }
                )
            elif t_ratio >= 0.70:
                raw_alerts.append(
                    {
                        "rule_code": "CUSUM_CRITICAL_TENSION",
                        "severity": "WARNING",
                        "lens_window": win,
                        "title": f"Tensión CUSUM alta en {win}v ({t_ratio:.0%} del umbral H)",
                        "message": (
                            f"La lente {win}v registra tensión acumulada de {t_vs_h} ({t_ratio:.0%} de H); "
                            "vigilar posible agotamiento de la curvatura actual."
                        ),
                        "metrics": {"tension_ratio": round(t_ratio, 3), "tension_vs_h": t_vs_h},
                        "anchor_ref": f"{win}v:warn70:{reg_start}:{last_date}",
                    }
                )

        # ── Regla 2: Quiebre estructural CUSUM reciente (<= 30 velas o < 15v) ────
        for lens_obj in (pri_lens, sen_lens):
            if not lens_obj.get("available"):
                continue
            win = int(lens_obj["window_candles"])
            uncons = cls._load_lens_unconsolidated_info(report_dir, win)
            if uncons and bool(uncons.get("detected")):
                b_date = str(uncons.get("break_date", last_date))
                c_since = int(uncons.get("candles_since_break") or 0)
                raw_alerts.append(
                    {
                        "rule_code": "RECENT_CUSUM_BREAK",
                        "severity": "CRITICAL",
                        "lens_window": win,
                        "title": f"Quiebre CUSUM fresco en consolidación ({win}v · hace {c_since}v)",
                        "message": (
                            f"Se detectó una ruptura CUSUM el {b_date} (hace {c_since} velas < 15v) en {win}v; "
                            "transición estructural en plena formación."
                        ),
                        "metrics": {"break_date": b_date, "candles_ago": c_since},
                        "anchor_ref": f"{win}v:uncons:{b_date}",
                    }
                )
                continue

            macro_breaks = lens_obj.get("macro_breaks") or []
            if macro_breaks:
                last_brk = macro_breaks[-1]
                c_idx = int(last_brk.get("candle_idx", 0))
                candles_ago = max(0, (win - 1) - c_idx)
                if candles_ago <= 30:
                    b_date = str(last_brk.get("date", last_date))[:10]
                    b_price = float(last_brk.get("price_at_break") or last_price)
                    is_up = "ALCISTA" in str(last_brk.get("break_type", "")).upper()
                    dir_lbl = "alcista" if is_up else "bajista"
                    raw_alerts.append(
                        {
                            "rule_code": "RECENT_CUSUM_BREAK",
                            "severity": "WARNING",
                            "lens_window": win,
                            "title": f"Nuevo régimen CUSUM {dir_lbl} reciente en {win}v ({b_date})",
                            "message": (
                                f"Ruptura estructural {dir_lbl} confirmada el {b_date} (hace {candles_ago}v "
                                f"en {b_price:,.2f}) sobre la lente {win}v."
                            ),
                            "metrics": {
                                "break_date": b_date,
                                "candles_ago": candles_ago,
                                "price_at_break": round(b_price, 4),
                            },
                            "anchor_ref": f"{win}v:brk30:{b_date}",
                        }
                    )

        # ── Regla 3: Pines tácticos del Sensor de Alerta 500v ────────────────────
        tac_detail = hier.get("tactical_sensor_detail") or {}
        for pin in tac_detail.get("pins") or []:
            p_kind = str(pin.get("kind", "PIN"))
            p_date = str(pin.get("date", last_date))[:10]
            c_ago = int(pin.get("candles_ago", 99))
            p_price = float(pin.get("price") or last_price)
            p_lbl = str(pin.get("label", f"Alerta 500v ({p_date})"))
            # Evitar duplicar con RECENT_CUSUM_BREAK si ya fue reportado con <=30v
            if p_kind == "CUSUM_BREAK" and c_ago <= 30:
                continue
            sev = "WARNING" if c_ago <= 20 else "INFO"
            raw_alerts.append(
                {
                    "rule_code": "TACTICAL_500V_PIN",
                    "severity": sev,
                    "lens_window": int(sen_lens.get("window_candles", 500)),
                    "title": p_lbl,
                    "message": (
                        f"Sensor táctico 500v mantiene pin activo ({p_kind}) del {p_date} "
                        f"(hace {c_ago} velas en {p_price:,.2f})."
                    ),
                    "metrics": {
                        "pin_kind": p_kind,
                        "date": p_date,
                        "candles_ago": c_ago,
                        "price": round(p_price, 4),
                    },
                    "anchor_ref": f"500v:{p_kind}:{p_date}",
                }
            )

        # ── Regla 4: Divergencia direccional entre lentes (2000v vs 1000v / 500v)
        if pri_lens.get("available") and ctx_lens.get("available"):
            pri_dir = str(pri_lens.get("raw_direction", ""))
            ctx_dir = str(ctx_lens.get("raw_direction", ""))
            pri_hr = pri_lens.get("human_regime") or {}
            ctx_hr = ctx_lens.get("human_regime") or {}
            pri_lbl = str(pri_hr.get("state_label") or pri_dir)
            ctx_lbl = str(ctx_hr.get("state_label") or ctx_dir)
            if pri_dir and ctx_dir and pri_dir != ctx_dir:
                sev_div = (
                    "INFO"
                    if pri_hr.get("state_code") == "LATERAL_DIGESTION"
                    else "WARNING"
                )
                reg_anchor = str(pri_lens.get("active_regime_start_date", last_date))
                raw_alerts.append(
                    {
                        "rule_code": "MULTI_LENS_DIVERGENCE",
                        "severity": sev_div,
                        "lens_window": int(pri_lens["window_candles"]),
                        "title": f"Desalineación macro-intermedia: 1000v ({pri_lbl}) vs. 2000v ({ctx_lbl})",
                        "message": (
                            f"El eje principal 1000v proyecta sesgo {pri_dir.lower()} ({pri_lbl}) mientras "
                            f"la marea estructural 2000v mantiene deriva {ctx_dir.lower()} ({ctx_lbl})."
                        ),
                        "metrics": {"primary_1000v_dir": pri_dir, "context_2000v_dir": ctx_dir},
                        "anchor_ref": f"div_2000_1000:{ctx_dir}_{pri_dir}:{reg_anchor}",
                    }
                )

        if pri_lens.get("available") and sen_lens.get("available"):
            pri_dir = str(pri_lens.get("raw_direction", ""))
            sen_dir = str(sen_lens.get("raw_direction", ""))
            pri_hr = pri_lens.get("human_regime") or {}
            sen_hr = sen_lens.get("human_regime") or {}
            pri_t150 = float((pri_lens.get("t150_summary") or {}).get("center_return_pct") or 0.0)
            sen_t150 = float((sen_lens.get("t150_summary") or {}).get("center_return_pct") or 0.0)
            if pri_dir and sen_dir and pri_dir != sen_dir and abs(pri_t150 - sen_t150) >= 20.0:
                sen_anchor = str(sen_lens.get("active_regime_start_date", last_date))
                sen_lbl = str(sen_hr.get("state_label") or sen_dir)
                pri_lbl = str(pri_hr.get("state_label") or pri_dir)
                raw_alerts.append(
                    {
                        "rule_code": "MULTI_LENS_DIVERGENCE",
                        "severity": "WARNING",
                        "lens_window": int(sen_lens["window_candles"]),
                        "title": f"Fractura táctica 500v ({sen_lbl}) frente a 1000v ({pri_lbl})",
                        "message": (
                            f"El pulso corto 500v ({sen_t150:+.1f}% a t+150) diverge con fuerza del eje "
                            f"1000v ({pri_t150:+.1f}% a t+150)."
                        ),
                        "metrics": {
                            "primary_t150_return_pct": round(pri_t150, 2),
                            "sensor_t150_return_pct": round(sen_t150, 2),
                        },
                        "anchor_ref": f"div_1000_500:{pri_dir}_{sen_dir}:{sen_anchor}",
                    }
                )

        # ── Regla 5: Estiramiento extremo Precio vs. Curva Suave ─────────────────
        for lens_obj, is_primary in ((pri_lens, True), (sen_lens, False)):
            if not lens_obj.get("available"):
                continue
            win = int(lens_obj["window_candles"])
            hr_obj = lens_obj.get("human_regime") or {}
            pos_code = str(hr_obj.get("position_code", "EN_LINEA"))
            gap_pct = float(lens_obj.get("price_vs_spline_gap_pct") or 0.0)
            thresh_pct = float(hr_obj.get("overextension_threshold_pct") or 2.5)
            if pos_code in ("SOBREEXTENDIDO", "DESCOLGADO") and (is_primary or abs(gap_pct) >= max(8.0, thresh_pct)):
                pos_word = "sobreextendido" if pos_code == "SOBREEXTENDIDO" else "descolgado"
                sev_st = "WARNING" if (is_primary or abs(gap_pct) >= 10.0) else "INFO"
                reg_anchor = str(lens_obj.get("active_regime_start_date", last_date))
                raw_alerts.append(
                    {
                        "rule_code": "CURVE_EXTREME_STRETCH",
                        "severity": sev_st,
                        "lens_window": win,
                        "title": f"Precio {pos_word} ({gap_pct:+.1f}%) respecto a su curva {win}v",
                        "message": (
                            f"El cierre actual ({last_price:,.2f}) se encuentra {pos_word} un {gap_pct:+.2f}% "
                            f"frente a la variedad suave de {win}v (umbral ±{thresh_pct:.2f}%)."
                        ),
                        "metrics": {
                            "gap_now_pct": round(gap_pct, 2),
                            "threshold_pct": round(thresh_pct, 2),
                            "position_code": pos_code,
                        },
                        "anchor_ref": f"stretch_{win}v:{pos_code}:{reg_anchor}",
                    }
                )

        # ── Regla 6: Transición de Estado Humano 1000v frente a corrida previa ───
        if previous_confluence and pri_lens.get("available"):
            prev_pri = cls._lens_by_role(previous_confluence, "PRINCIPAL_PREDICTIVA") or {}
            if prev_pri.get("available"):
                prev_hr = prev_pri.get("human_regime") or {}
                curr_hr = pri_lens.get("human_regime") or {}
                prev_code = str(prev_hr.get("state_code") or prev_pri.get("raw_direction") or "")
                curr_code = str(curr_hr.get("state_code") or pri_lens.get("raw_direction") or "")
                if prev_code and curr_code and prev_code != curr_code:
                    prev_lbl = str(prev_hr.get("state_label") or prev_code)
                    curr_lbl = str(curr_hr.get("state_label") or curr_code)
                    raw_alerts.append(
                        {
                            "rule_code": "REGIME_STATE_TRANSITION",
                            "severity": "WARNING",
                            "lens_window": int(pri_lens["window_candles"]),
                            "title": f"Cambio de estado en 1000v: {prev_lbl} → {curr_lbl}",
                            "message": (
                                f"La lente principal 1000v transitó desde '{prev_lbl}' en la lectura previa "
                                f"hacia '{curr_lbl}' al cierre del {last_date}."
                            ),
                            "metrics": {"previous_state": prev_code, "current_state": curr_code},
                            "anchor_ref": f"trans_1000v:{prev_code}_to_{curr_code}:{last_date}",
                        }
                    )

        # Ordenar de mayor a menor severidad y aplicar deduplicación en Ledger
        raw_alerts.sort(key=lambda a: SEVERITY_RANK.get(a["severity"], 0), reverse=True)

        enriched_alerts: List[Dict[str, Any]] = []
        for item in raw_alerts:
            fp = cls.compute_fingerprint(
                ticker=ticker,
                interval=interval,
                rule_code=item["rule_code"],
                anchor_ref=item["anchor_ref"],
            )
            if ledger is not None:
                is_new, first_seen = ledger.mark_and_check_is_new(
                    fingerprint=fp,
                    ticker=ticker,
                    rule_code=item["rule_code"],
                    run_key=run_key,
                )
            else:
                is_new = True
                first_seen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            enriched_alerts.append(
                {
                    "fingerprint": fp,
                    "is_new": bool(is_new),
                    "first_seen_utc": first_seen,
                    "ticker": ticker,
                    "interval": interval,
                    "last_date": last_date,
                    "rule_code": item["rule_code"],
                    "severity": item["severity"],
                    "lens_window": item["lens_window"],
                    "title": item["title"],
                    "message": item["message"],
                    "metrics": item["metrics"],
                }
            )

        if ledger is not None:
            ledger.save()

        highest_sev = enriched_alerts[0]["severity"] if enriched_alerts else "NONE"
        new_count = sum(1 for a in enriched_alerts if a["is_new"])

        return {
            "schema_version": cls.SCHEMA_VERSION,
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ticker": ticker,
            "interval": interval,
            "last_date": last_date,
            "last_close_price": round(last_price, 4),
            "total_active_alerts": len(enriched_alerts),
            "new_alerts_count": int(new_count),
            "highest_severity": highest_sev,
            "alerts": enriched_alerts,
        }

    @classmethod
    def evaluate_directory(
        cls,
        report_dir: Path,
        ledger_path: Optional[Path] = None,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evalúa `report_dir/confluence.json`, persiste `alerts.json` y envía webhook si aplica."""
        rep = Path(report_dir).resolve()
        conf_path = rep / "confluence.json"
        if not conf_path.is_file():
            raise FileNotFoundError(f"No existe confluence.json en {rep}")

        with open(conf_path, "r", encoding="utf-8") as f:
            confluence = json.load(f)

        prev_conf = cls.find_previous_confluence(rep)
        eff_ledger_path = Path(ledger_path).resolve() if ledger_path else cls.resolve_default_ledger_path(rep)
        ledger = AlertLedger(eff_ledger_path)

        payload = cls.evaluate_confluence(
            confluence=confluence,
            previous_confluence=prev_conf,
            report_dir=rep,
            ledger=ledger,
            run_key=str(rep),
        )

        if webhook_url:
            wh_result = cls.dispatch_webhook(webhook_url=webhook_url, alerts_payload=payload, only_new=True)
            payload["webhook_dispatch"] = wh_result

        alerts_path = rep / "alerts.json"
        with open(alerts_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return payload

    @staticmethod
    def dispatch_webhook(
        webhook_url: str,
        alerts_payload: Dict[str, Any],
        only_new: bool = True,
        timeout_sec: float = 5.0,
    ) -> Dict[str, Any]:
        """Envía alertas por HTTP POST JSON estándar (`urllib.request`, sin dependencias externas)."""
        candidates = [
            a for a in alerts_payload.get("alerts", []) if (not only_new or bool(a.get("is_new")))
        ]
        if not candidates:
            return {"sent": False, "dispatched_count": 0, "reason": "no_new_alerts"}

        ticker = alerts_payload.get("ticker", "ASSET")
        lines = [f"[KineTopus Alert · {ticker}] {len(candidates)} alerta(s) activa(s):"]
        for a in candidates[:5]:
            lines.append(f"- [{a['severity']}] {a['title']}")

        body_obj = {
            "text": "\n".join(lines),
            "ticker": ticker,
            "last_date": alerts_payload.get("last_date"),
            "last_close_price": alerts_payload.get("last_close_price"),
            "dispatched_count": len(candidates),
            "alerts": candidates,
        }
        encoded = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=webhook_url,
            data=encoded,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "KineTopus-Analyst/0.4.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                status_code = int(getattr(resp, "status", 200))
            return {
                "sent": 200 <= status_code < 300,
                "status_code": status_code,
                "dispatched_count": len(candidates),
            }
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return {
                "sent": False,
                "dispatched_count": 0,
                "error": str(exc),
            }
