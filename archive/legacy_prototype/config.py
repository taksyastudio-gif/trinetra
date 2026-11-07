"""
TRINETRA Configuration Module
Defines system parameters, thresholds, and operational flags.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class SpatialConfig:
    """Configuration for spatial positioning zones and proximity thresholds."""
    # Horizontal zone partition ratios (normalized 0.0 to 1.0)
    # [0.0, left_zone_boundary) -> LEFT
    # [left_zone_boundary, right_zone_boundary] -> CENTER (Straight Ahead)
    # (right_zone_boundary, 1.0] -> RIGHT
    left_zone_boundary: float = 0.35
    right_zone_boundary: float = 0.65

    # Proximity estimation based on normalized bounding box height (0.0 to 1.0)
    # Obstacles occupying > immediate_height_ratio are considered very close
    immediate_height_ratio: float = 0.42
    approaching_height_ratio: float = 0.22

    # Bottom viewport cutoff: if bottom y2 > bottom_proximity_ratio, obstacle is at user's feet/ground
    bottom_proximity_ratio: float = 0.85


@dataclass
class TTSConfig:
    """Configuration for Text-to-Speech audio queue and rate-limiting."""
    rate: int = 175  # Words per minute
    volume: float = 1.0  # 0.0 to 1.0
    voice_index: int = 0  # Voice selection index
    mute_audio: bool = False  # Mute audio output (visual debug only)

    # Cooldown durations in seconds to avoid alert spamming
    default_cooldown_sec: float = 4.0
    critical_cooldown_sec: float = 2.0
    approaching_cooldown_sec: float = 3.5
    distant_cooldown_sec: float = 6.0

    # Max items in speech priority queue before dropping oldest low-priority alerts
    max_queue_size: int = 20


@dataclass
class DetectorConfig:
    """Configuration for YOLOv8 edge object detector."""
    model_path: str = "yolov8n.pt"
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.45
    device: str = "cpu"  # 'cpu', 'cuda', 'mps'
    use_mock: bool = False  # Force mock detector for testing/headless

    # Filter for critical navigation obstacle classes (COCO class names)
    # If None, all detected classes will be processed
    navigation_classes: Optional[List[str]] = field(default_factory=lambda: [
        "person", "bicycle", "car", "motorcycle", "bus", "truck", "traffic light",
        "stop sign", "bench", "dog", "chair", "couch", "potted plant", "bed",
        "dining table", "toilet", "tv", "door", "stairs", "pole", "fire hydrant"
    ])


@dataclass
class VisualizerConfig:
    """Configuration for OpenCV visual debug window overlay."""
    window_name: str = "TRINETRA - Vision & Navigation Engine"
    show_window: bool = True
    show_zones: bool = True
    show_bboxes: bool = True
    show_hud: bool = True
    show_speech_log: bool = True
    overlay_alpha: float = 0.3
    font_scale: float = 0.55
    window_size: Tuple[int, int] = (960, 540)


@dataclass
class EngineConfig:
    """Master configuration container for TRINETRA backend engine."""
    video_source: str = "0"  # Camera index "0" or video file/RTSP URL
    frame_width: int = 640
    frame_height: int = 480
    target_fps: int = 30
    headless: bool = False

    spatial: SpatialConfig = field(default_factory=SpatialConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    visualizer: VisualizerConfig = field(default_factory=VisualizerConfig)
