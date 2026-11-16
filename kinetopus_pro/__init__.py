"""
KineTopus-Analyst (`kinetopus_pro`): Suite cuantitativa Headless Multi-Lente (`v0.4.0`),
Enfoque Geométrico Puro, Proyección Simultánea t+150 en 3 Lentes (2000v Cian, 1000v Ámbar, 500v Violeta),
Indicador Portable B2B (`indicator_feed.json` / `widget.html` / `indicator.pine`), Alertas Activas
y Micro-Servicio HTTP / MCP (`kinetopus-serve`, `kinetopus-mcp`).
Construido en arquitectura Open-Core sobre la librería pública `kinetopus-engine`.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.4.0"

DEFAULT_MULTI_LENSES = (2000, 1000, 500)

__all__ = [
    "__version__",
    "AlertLedger",
    "DEFAULT_MULTI_LENSES",
    "HeadlessRunResult",
    "KinetopusAlertEngine",
    "KinetopusAnalysisConfig",
    "KinetopusHeadlessPipeline",
    "KinetopusIndicatorExporter",
    "KinetopusMultiLensRunner",
    "KinetopusReportBuilder",
    "KinetopusStaticRenderer",
    "LensSlotResult",
    "MultiLensConfig",
    "MultiLensRunResult",
]

_LAZY_EXPORTS = {
    "AlertLedger": ("kinetopus_pro.alerts", "AlertLedger"),
    "KinetopusAlertEngine": ("kinetopus_pro.alerts", "KinetopusAlertEngine"),
    "HeadlessRunResult": ("kinetopus_pro.headless_pipeline", "HeadlessRunResult"),
    "KinetopusAnalysisConfig": ("kinetopus_pro.headless_pipeline", "KinetopusAnalysisConfig"),
    "KinetopusHeadlessPipeline": ("kinetopus_pro.headless_pipeline", "KinetopusHeadlessPipeline"),
    "KinetopusIndicatorExporter": ("kinetopus_pro.indicator_export", "KinetopusIndicatorExporter"),
    "KinetopusMultiLensRunner": ("kinetopus_pro.multi_lens", "KinetopusMultiLensRunner"),
    "LensSlotResult": ("kinetopus_pro.multi_lens", "LensSlotResult"),
    "MultiLensConfig": ("kinetopus_pro.multi_lens", "MultiLensConfig"),
    "MultiLensRunResult": ("kinetopus_pro.multi_lens", "MultiLensRunResult"),
    "KinetopusReportBuilder": ("kinetopus_pro.report_builder", "KinetopusReportBuilder"),
    "KinetopusStaticRenderer": ("kinetopus_pro.static_renderer", "KinetopusStaticRenderer"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is not None:
        import importlib

        mod = importlib.import_module(target[0])
        val = getattr(mod, target[1])
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
