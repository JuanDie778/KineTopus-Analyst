"""
KineTopus-Pro: Suite cuantitativa Headless, Radar de Regímenes y Protocolo Agéntico.
Construido en arquitectura Open-Core sobre la librería pública `kinetopus-engine`.
"""

from kinetopus_pro.headless_pipeline import (
    HeadlessRunResult,
    KinetopusAnalysisConfig,
    KinetopusHeadlessPipeline,
)
from kinetopus_pro.static_renderer import KinetopusStaticRenderer

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "HeadlessRunResult",
    "KinetopusAnalysisConfig",
    "KinetopusHeadlessPipeline",
    "KinetopusStaticRenderer",
]
