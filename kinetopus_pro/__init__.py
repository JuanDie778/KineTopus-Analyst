"""
KineTopus-Analyst (`kinetopus_pro`): Suite cuantitativa Headless Multi-Lente (v0.3.1 — Enfoque Geométrico Puro),
Proyección Simultánea t+150 en 3 Lentes (2000v Cian, 1000v Ámbar, 500v Violeta), Conos Calibrados,
Walk-Forward Opcional (`--audit-oos`) y Motor Dual de Presentación (`report.html` + `analysis.md`).
Construido en arquitectura Open-Core sobre la librería pública `kinetopus-engine`.
"""

from kinetopus_pro.headless_pipeline import (
    HeadlessRunResult,
    KinetopusAnalysisConfig,
    KinetopusHeadlessPipeline,
)
from kinetopus_pro.multi_lens import (
    DEFAULT_MULTI_LENSES,
    KinetopusMultiLensRunner,
    LensSlotResult,
    MultiLensConfig,
    MultiLensRunResult,
)
from kinetopus_pro.report_builder import KinetopusReportBuilder
from kinetopus_pro.static_renderer import KinetopusStaticRenderer

__version__ = "0.3.1"

__all__ = [
    "__version__",
    "DEFAULT_MULTI_LENSES",
    "HeadlessRunResult",
    "KinetopusAnalysisConfig",
    "KinetopusHeadlessPipeline",
    "KinetopusMultiLensRunner",
    "KinetopusReportBuilder",
    "KinetopusStaticRenderer",
    "LensSlotResult",
    "MultiLensConfig",
    "MultiLensRunResult",
]
