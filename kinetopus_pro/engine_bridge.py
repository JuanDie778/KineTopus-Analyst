"""
Adaptador Open-Core hacia `kinetopus-engine`.
Centraliza todas las importaciones del núcleo físico público para desacoplar `kinetopus_pro`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from src.quant_engine.auto_tuner import CUSUMAutoTuner
    from src.quant_engine.blender import ContinuousBlender
    from src.quant_engine.nervous import RegimeShiftDetector
    from src.quant_engine.physics import PhysicsDiscoverer
    from src.quant_engine.sensor import SpectralAnalyzer
    from src.quant_engine.symbolic import SymbolicTranslator
    from src.ui.market_loader import MarketLoader
except ModuleNotFoundError:
    fallback_dir = Path(
        os.environ.get(
            "KINETOPUS_ENGINE_DIR",
            str(Path(__file__).resolve().parents[2] / "KineTopus Engine"),
        )
    )
    if fallback_dir.is_dir() and str(fallback_dir) not in sys.path:
        sys.path.insert(0, str(fallback_dir))
    from src.quant_engine.auto_tuner import CUSUMAutoTuner
    from src.quant_engine.blender import ContinuousBlender
    from src.quant_engine.nervous import RegimeShiftDetector
    from src.quant_engine.physics import PhysicsDiscoverer
    from src.quant_engine.sensor import SpectralAnalyzer
    from src.quant_engine.symbolic import SymbolicTranslator
    from src.ui.market_loader import MarketLoader

__all__ = [
    "CUSUMAutoTuner",
    "ContinuousBlender",
    "MarketLoader",
    "PhysicsDiscoverer",
    "RegimeShiftDetector",
    "SpectralAnalyzer",
    "SymbolicTranslator",
]
