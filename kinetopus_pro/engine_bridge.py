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
except ModuleNotFoundError as exc:
    _repo_parent = Path(__file__).resolve().parents[2]
    _candidates: list[Path] = []
    _env_dir = os.environ.get("KINETOPUS_ENGINE_DIR", "").strip()
    if _env_dir:
        _candidates.append(Path(_env_dir))
    _candidates.extend(
        [
            _repo_parent / "KineTopus-Engine",
            _repo_parent / "KineTopus Engine",
        ]
    )
    for _candidate in _candidates:
        if _candidate.is_dir() and (_candidate / "src").is_dir():
            if str(_candidate) not in sys.path:
                sys.path.insert(0, str(_candidate))
            break
    try:
        from src.quant_engine.auto_tuner import CUSUMAutoTuner
        from src.quant_engine.blender import ContinuousBlender
        from src.quant_engine.nervous import RegimeShiftDetector
        from src.quant_engine.physics import PhysicsDiscoverer
        from src.quant_engine.sensor import SpectralAnalyzer
        from src.quant_engine.symbolic import SymbolicTranslator
        from src.ui.market_loader import MarketLoader
    except ModuleNotFoundError as inner_exc:
        raise ModuleNotFoundError(
            "No se encontró el núcleo científico 'kinetopus-engine'. "
            "Instálalo con: pip install \"git+https://github.com/JuanDie778/KineTopus-Engine.git\" "
            "o define KINETOPUS_ENGINE_DIR apuntando al clon local de KineTopus-Engine."
        ) from inner_exc

__all__ = [
    "CUSUMAutoTuner",
    "ContinuousBlender",
    "MarketLoader",
    "PhysicsDiscoverer",
    "RegimeShiftDetector",
    "SpectralAnalyzer",
    "SymbolicTranslator",
]
