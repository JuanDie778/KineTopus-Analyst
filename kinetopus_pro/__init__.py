"""
KineTopus-Analyst (`kinetopus_pro`): Suite cuantitativa Headless Multi-Lente,
Radar Jerárquico de Regímenes, Sellos Estrictos OOS y Protocolo Agéntico.
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
from kinetopus_pro.static_renderer import KinetopusStaticRenderer

__version__ = "0.2.0"

__all__ = [
    "__version__",
    "DEFAULT_MULTI_LENSES",
    "HeadlessRunResult",
    "KinetopusAnalysisConfig",
    "KinetopusHeadlessPipeline",
    "KinetopusMultiLensRunner",
    "KinetopusStaticRenderer",
    "LensSlotResult",
    "MultiLensConfig",
    "MultiLensRunResult",
]
