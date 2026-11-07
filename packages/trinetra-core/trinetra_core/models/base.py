"""
Model Strategy and Abstraction Interfaces for TRINETRA v2.
Allows any model to be benchmarked, swapped, or quantized behind a clean contract.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ModelMetadata:
    """Documented provenance, licensing, and bias audit for every deployed model."""
    name: str
    version: str
    architecture: str
    framework: str                        # "onnx", "tesseract", "piper", "pytorch"
    license: str                          # "Apache-2.0", "MIT", "CC-BY-4.0"
    origin_dataset: str                   # e.g., "COCO 2017", "WIDER FACE"
    nepal_bias_notes: str
    supported_classes: List[str] = field(default_factory=list)
    input_resolution: Optional[Tuple[int, int]] = None
    target_device_tier: str = "all"       # "full", "standard", "lite", "all"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "architecture": self.architecture,
            "framework": self.framework,
            "license": self.license,
            "origin_dataset": self.origin_dataset,
            "nepal_bias_notes": self.nepal_bias_notes,
            "supported_classes": self.supported_classes,
            "input_resolution": list(self.input_resolution) if self.input_resolution else None,
            "target_device_tier": self.target_device_tier,
        }


class BaseModelInterface(ABC):
    """
    Abstract interface for all swappable edge models.
    """

    @abstractmethod
    def load(self, model_path: str, execution_provider: str = "CPU", num_threads: int = 2) -> bool:
        """Load model weights and initialize inference session."""
        pass

    @abstractmethod
    def predict(self, inputs: Any) -> Any:
        """Execute inference against input payload."""
        pass

    @abstractmethod
    def unload(self) -> None:
        """Release session memory and tensors."""
        pass

    @abstractmethod
    def is_loaded(self) -> bool:
        """Return True if model is loaded and ready."""
        pass

    @property
    @abstractmethod
    def metadata(self) -> ModelMetadata:
        """Return model metadata and audit provenance."""
        pass

    @abstractmethod
    def get_average_latency_ms(self) -> float:
        """Return rolling average inference latency."""
        pass
