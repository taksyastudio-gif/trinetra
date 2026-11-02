"""
Trinetra Object Detection Package
"""
from app.detection.engine import (
    BoundingBox,
    Detection,
    DetectionResult,
    DetectionEngine,
    FakeDetectionEngine,
    UnavailableDetectionEngine,
    PerceptionPipeline,
    classify_sector,
)
from app.detection.onnx_engine import (
    OnnxDetectionEngine,
    ModelError,
    ModelNotFoundError,
    ModelIntegrityError,
    InferenceRuntimeError,
    verify_model_hash,
    validate_bounding_box,
    COCO_CLASSES,
)
from app.detection.tracking import (
    TrackState,
    MovementDirection,
    TrackedObject,
    TemporalTracker,
    compute_iou,
)
from app.detection.scene import (
    CollisionRisk,
    WalkablePath,
    SceneAssessment,
    SceneAnalyzer,
)
from app.detection.decision import (
    SceneDecisionEngine,
)

__all__ = [
    "BoundingBox",
    "Detection",
    "DetectionResult",
    "DetectionEngine",
    "FakeDetectionEngine",
    "UnavailableDetectionEngine",
    "PerceptionPipeline",
    "classify_sector",
    "OnnxDetectionEngine",
    "ModelError",
    "ModelNotFoundError",
    "ModelIntegrityError",
    "InferenceRuntimeError",
    "verify_model_hash",
    "validate_bounding_box",
    "COCO_CLASSES",
    "TrackState",
    "MovementDirection",
    "TrackedObject",
    "TemporalTracker",
    "compute_iou",
    "CollisionRisk",
    "WalkablePath",
    "SceneAssessment",
    "SceneAnalyzer",
    "SceneDecisionEngine",
]

