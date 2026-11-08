"""
Trinetra Scene Decision Engine Layer
Dedicated decision orchestrator sitting between visual scene perception and SpeechManager.
Applies temporal confirmation, multi-object crowd aggregation, hazard priority preemption,
honest confidence thresholds, and deduplication so the system never chatters indiscriminately.
"""

import logging
import time
from typing import Any, Dict, Optional

from app.audio.speaker import SpeechManager, SpeechPriority
from app.detection.scene import CollisionRisk, SceneAssessment, VEHICLE_CLASSES
from app.detection.tracking import MovementDirection
from app.detection.trajectory import CrossingDirection, TrajectoryClassification
from app.localization import (
    DEFAULT_LANGUAGE,
    format_announcement,
    format_approaching_announcement,
    format_crowd_announcement,
    format_crossing_announcement,
    format_multi_announcement,
    format_path_advisory,
    format_path_intersection_announcement,
    get_announcement_key,
    is_supported_language,
    normalize_language,
)

logger = logging.getLogger("trinetra.decision")


class SceneDecisionEngine:
    """
    Synthesizes temporal scene assessments into concise, prioritized spoken announcements.
    Adheres strictly to the core principle:
    - Interprets observations over time rather than narrating every single detected box.
    - Summarizes crowded scenes rather than announcing every person.
    - Prioritizes collision hazards with preemption.
    - Issues directional advisories only when supported by visual clearance.
    """

    def __init__(
        self,
        speech_manager: Optional[SpeechManager] = None,
        language: str = DEFAULT_LANGUAGE,
        default_cooldown: float = 3.5,
        crowd_cooldown: float = 6.0,
        hazard_cooldown: float = 2.0,
        path_cooldown: float = 5.0,
        min_announcement_interval: float = 1.5,
    ):
        self.speech_manager = speech_manager
        self._language = normalize_language(language) if is_supported_language(language) else language.strip().lower()
        self.default_cooldown = default_cooldown
        self.crowd_cooldown = crowd_cooldown
        self.hazard_cooldown = hazard_cooldown
        self.path_cooldown = path_cooldown
        self.min_announcement_interval = min_announcement_interval

        self._cooldowns: Dict[str, float] = {}
        self._events_dispatched_count = 0
        self._last_crowd_state: bool = False
        self._last_crowd_count: int = 0
        self._last_path_direction: Optional[str] = None
        self._last_announcement_time: float = -1000.0

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        norm = normalize_language(value) if is_supported_language(value) else value.strip().lower()
        if norm != self._language:
            self._language = norm
            self._last_announcement_time = -1000.0
            self._last_path_direction = None

    def process_scene(
        self,
        assessment: SceneAssessment,
        current_time: Optional[float] = None
    ) -> Optional[str]:
        """
        Evaluates a SceneAssessment and dispatches at most one prioritized spoken event.
        Suppresses unchanged scenes, prevents repeated stationary chattering,
        and ensures meaningful position/hazard changes are voiced immediately.
        Returns the event type dispatched, or None if suppressed.
        """
        if not self.speech_manager:
            return None

        lang = self.language
        now = current_time if current_time is not None else time.time()

        # ---------------------------------------------------------------------
        # Priority 1: Critical Emergency Hazard (Preempts all ongoing audio)
        # ---------------------------------------------------------------------
        if assessment.highest_risk == CollisionRisk.CRITICAL and assessment.critical_track:
            track = assessment.critical_track
            key = f"hazard:{track.class_name}:{track.sector}:{lang}"

            if (now - self._cooldowns.get(key, 0.0)) >= self.hazard_cooldown:
                self._cooldowns[key] = now
                if track.movement == MovementDirection.APPROACHING:
                    text = format_approaching_announcement(track.class_name, track.sector, language=lang)
                else:
                    text = "सावधान! अगाडि अवरोध छ।" if lang == "ne" else "Caution! Obstacle directly ahead."

                self.speech_manager.announce(
                    text=text,
                    priority=SpeechPriority.CRITICAL_HAZARD,
                    message_key=key,
                    interrupt=True,
                    cooldown=self.hazard_cooldown,
                    language=lang,
                )
                track.mark_announced(now, language=lang)
                self._last_announcement_time = now
                self._events_dispatched_count += 1
                return "critical_hazard"

        # ---------------------------------------------------------------------
        # Priority 2: Path Intersection Hazard (Object crossing/moving into walking corridor)
        # ---------------------------------------------------------------------
        if assessment.path_intersecting_objects:
            path_candidates = [
                t for t in assessment.path_intersecting_objects
                if (not t.announced)
                or (t.last_announced_trajectory != TrajectoryClassification.PATH_INTERSECTION)
                or t.has_meaningfully_changed(language=lang)
            ]
            if path_candidates:
                top_path_track = max(path_candidates, key=lambda t: t.height)
                crossing_dir = top_path_track.trajectory.crossing_direction.value if top_path_track.trajectory else None
                path_key = f"path_intersect:{top_path_track.track_id}:{top_path_track.class_name}:{lang}"

                if (now - self._cooldowns.get(path_key, 0.0)) >= self.hazard_cooldown:
                    self._cooldowns[path_key] = now
                    text = format_path_intersection_announcement(
                        top_path_track.class_name,
                        direction=crossing_dir,
                        language=lang
                    )
                    is_vehicle = top_path_track.class_name in VEHICLE_CLASSES
                    self.speech_manager.announce(
                        text=text,
                        priority=SpeechPriority.CRITICAL_HAZARD if is_vehicle else SpeechPriority.SPATIAL_NAVIGATION,
                        message_key=path_key,
                        interrupt=is_vehicle,
                        cooldown=self.hazard_cooldown,
                        language=lang,
                    )
                    top_path_track.mark_announced(now, language=lang)
                    self._last_announcement_time = now
                    self._events_dispatched_count += 1
                    return "path_intersection"

        # ---------------------------------------------------------------------
        # Priority 3: Lateral Crossing Obstacles (Outside immediate corridor)
        # ---------------------------------------------------------------------
        if assessment.crossing_objects:
            crossing_candidates = [
                t for t in assessment.crossing_objects
                if (not t.announced)
                or (t.last_announced_trajectory != TrajectoryClassification.CROSSING)
                or t.has_meaningfully_changed(language=lang)
            ]
            if crossing_candidates:
                top_crossing = max(crossing_candidates, key=lambda t: t.height)
                crossing_dir = top_crossing.trajectory.crossing_direction.value if top_crossing.trajectory else "left_to_right"
                crossing_key = f"crossing:{top_crossing.track_id}:{top_crossing.class_name}:{crossing_dir}:{lang}"

                if (now - self._cooldowns.get(crossing_key, 0.0)) >= self.default_cooldown:
                    self._cooldowns[crossing_key] = now
                    text = format_crossing_announcement(
                        top_crossing.class_name,
                        direction=crossing_dir,
                        language=lang
                    )
                    self.speech_manager.announce(
                        text=text,
                        priority=SpeechPriority.SPATIAL_NAVIGATION,
                        message_key=crossing_key,
                        interrupt=False,
                        cooldown=self.default_cooldown,
                        language=lang,
                    )
                    top_crossing.mark_announced(now, language=lang)
                    self._last_announcement_time = now
                    self._events_dispatched_count += 1
                    return "crossing_obstacle"

        # ---------------------------------------------------------------------
        # Priority 4: Crowd Event (Synthesizes multiple persons into a concise summary)
        # ---------------------------------------------------------------------
        if assessment.is_crowded:
            # Mark all confirmed persons as accounted for by the crowd summary
            for t in assessment.confirmed_tracks:
                if t.class_name == "person":
                    t.announced = True
                    t.last_announced_sector = t.sector
                    t.last_announced_box = t.box
                    t.last_announced_movement = t.movement
                    t.last_announced_time = now
                    t.last_announced_language = lang

            crowd_state_changed = not self._last_crowd_state
            crowd_count_changed = abs(assessment.crowd_count - self._last_crowd_count) >= 3
            crowd_key = f"crowd:{lang}"

            if (crowd_state_changed or crowd_count_changed) and (now - self._cooldowns.get(crowd_key, 0.0)) >= self.crowd_cooldown:
                self._cooldowns[crowd_key] = now
                self._last_crowd_state = True
                self._last_crowd_count = assessment.crowd_count
                text = format_crowd_announcement(assessment.crowd_count, language=lang)
                self.speech_manager.announce(
                    text=text,
                    priority=SpeechPriority.SPATIAL_NAVIGATION,
                    message_key=crowd_key,
                    interrupt=False,
                    cooldown=self.crowd_cooldown,
                    language=lang,
                )
                self._last_announcement_time = now
                self._events_dispatched_count += 1
                return "crowd_summary"
        else:
            self._last_crowd_state = False
            self._last_crowd_count = 0

        # ---------------------------------------------------------------------
        # Priority 3: Approaching Dynamic Obstacles
        # ---------------------------------------------------------------------
        if assessment.approaching_objects:
            approaching_candidates = [
                t for t in assessment.approaching_objects
                if (not t.announced)
                or (t.last_announced_movement != MovementDirection.APPROACHING)
                or (t.sector != t.last_announced_sector)
                or t.has_meaningfully_changed(language=lang)
            ]
            if approaching_candidates:
                top_approaching = max(approaching_candidates, key=lambda t: t.height)
                appr_key = f"approaching:{top_approaching.track_id}:{top_approaching.class_name}:{lang}"

                if (now - self._cooldowns.get(appr_key, 0.0)) >= self.default_cooldown:
                    self._cooldowns[appr_key] = now
                    text = format_approaching_announcement(
                        top_approaching.class_name,
                        top_approaching.sector,
                        language=lang
                    )
                    self.speech_manager.announce(
                        text=text,
                        priority=SpeechPriority.SPATIAL_NAVIGATION,
                        message_key=appr_key,
                        interrupt=False,
                        cooldown=self.default_cooldown,
                        language=lang,
                    )
                    top_approaching.mark_announced(now, language=lang)
                    self._last_announcement_time = now
                    self._events_dispatched_count += 1
                    return "approaching_obstacle"

        # ---------------------------------------------------------------------
        # Priority 4: Significant Obstacle Identification (Event-based Persistent Tracking)
        # ---------------------------------------------------------------------
        # Self-presence / Laptop Mode filter:
        # If a single person occupies > 50% of the screen area or > 80% height right in front of the camera,
        # it is the user themselves seated at the desk/laptop. Suppress looping "अगाडि मान्छे छ".
        is_laptop_self_view = False
        if not assessment.is_crowded and len(assessment.confirmed_tracks) <= 2:
            for t in assessment.confirmed_tracks:
                b_height = (t.box.y_max - t.box.y_min) if t.box else 0.0
                b_area = t.box.area if t.box else 0.0
                if t.class_name == "person" and (b_area >= 0.45 or b_height >= 0.75):
                    is_laptop_self_view = True
                    break

        if assessment.is_crowded:
            # When crowded, persons are summarized collectively; only non-person obstacles are candidates
            candidate_tracks = [
                t for t in assessment.confirmed_tracks
                if t.class_name not in ("person", "uncertain", "unknown") and t.has_meaningfully_changed(language=lang)
            ]
        elif is_laptop_self_view:
            # Self-user view active: ignore the person, only announce objects held up or placed in front (like currency)
            candidate_tracks = [
                t for t in assessment.confirmed_tracks
                if t.class_name not in ("person", "uncertain", "unknown") and t.has_meaningfully_changed(language=lang)
            ]
        else:
            candidate_tracks = [
                t for t in assessment.confirmed_tracks
                if t.class_name not in ("uncertain", "unknown") and t.has_meaningfully_changed(language=lang)
            ]

        if candidate_tracks:
            candidate_tracks.sort(
                key=lambda t: (
                    1 if t.sector == "center" else 0,
                    t.height,
                    t.confidence
                ),
                reverse=True
            )
            top_track = candidate_tracks[0]

            # Semantic key independent of ephemeral tracker IDs prevents looping chatter
            semantic_key = f"stationary:{top_track.class_name}:{top_track.sector}:{lang}"

            # Suppress if this stationary obstacle was recently announced
            last_spoken = self._cooldowns.get(semantic_key, 0.0)
            if (now - last_spoken) < self.default_cooldown:
                top_track.mark_announced(now, language=lang)
                return None

            if (now - self._last_announcement_time) >= self.min_announcement_interval:
                self._cooldowns[semantic_key] = now
                self._last_announcement_time = now
                text = format_announcement(top_track.class_name, top_track.sector, language=lang)
                self.speech_manager.announce(
                    text=text,
                    priority=SpeechPriority.SPATIAL_NAVIGATION,
                    message_key=semantic_key,
                    interrupt=False,
                    cooldown=self.default_cooldown,
                    language=lang,
                )
                top_track.mark_announced(now, language=lang)
                self._events_dispatched_count += 1
                return "stationary_obstacle"

        # ---------------------------------------------------------------------
        # Priority 5: Path Clearance Advisory (Center obstructed, flank clear)
        # ---------------------------------------------------------------------
        # Suppress path clearance advice during stationary laptop self-view (user is working at a desk)
        if not assessment.path.center_clear and not is_laptop_self_view:
            rec_dir = assessment.path.recommended_direction
            if rec_dir in ("left", "right") and assessment.path.confidence >= 0.70:
                direction_changed = (rec_dir != self._last_path_direction)
                path_key = f"path_advisory:{rec_dir}:{lang}"
                # Increase path cooldown from 5s to 12s so it doesn't loop incessantly
                effective_path_cooldown = max(self.path_cooldown, 12.0)
                if (
                    direction_changed
                    and (now - self._cooldowns.get(path_key, 0.0)) >= effective_path_cooldown
                    and (now - self._last_announcement_time) >= self.min_announcement_interval
                ):
                    self._cooldowns[path_key] = now
                    self._last_path_direction = rec_dir
                    self._last_announcement_time = now
                    text = format_path_advisory(rec_dir, language=lang)
                    self.speech_manager.announce(
                        text=text,
                        priority=SpeechPriority.SPATIAL_NAVIGATION,
                        message_key=path_key,
                        interrupt=False,
                        cooldown=effective_path_cooldown,
                        language=lang,
                    )
                    self._events_dispatched_count += 1
                    return "path_advisory"
        else:
            self._last_path_direction = None

        return None

    def reset(self) -> None:
        """Clears all event cooldowns and state history."""
        self._cooldowns.clear()
        self._events_dispatched_count = 0
        self._last_crowd_state = False
        self._last_crowd_count = 0
        self._last_path_direction = None
        self._last_announcement_time = -1000.0
