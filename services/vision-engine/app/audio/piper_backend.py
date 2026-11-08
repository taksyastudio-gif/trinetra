"""
Trinetra Piper Speech Backend & Composite Routing Engine
Provides local neural speech synthesis for Nepali using Piper TTS (ne_NP-google-x_low)
and routes English speech to Windows SAPI, preserving priority preemption and instant stop.
"""

import json
import logging
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Set
import wave

from app.audio.speaker import SpeechBackend, WindowsSapiSpeechBackend

logger = logging.getLogger("trinetra.audio.piper")

# Default production asset locations within services/vision-engine
_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PIPER_EXE = _SERVICE_ROOT / "runtime" / "piper" / "piper.exe"
DEFAULT_MODEL_PATH = _SERVICE_ROOT / "models" / "tts" / "ne_NP-google-x_low.onnx"
DEFAULT_CONFIG_PATH = _SERVICE_ROOT / "models" / "tts" / "ne_NP-google-x_low.onnx.json"
DEFAULT_HAZARD_WAV = _SERVICE_ROOT / "models" / "tts" / "hazard_nepali.wav"

# Fallback development locations (root/test_piper_poc)
_FALLBACK_ROOT = _SERVICE_ROOT.parent.parent / "test_piper_poc"
FALLBACK_PIPER_EXE = _FALLBACK_ROOT / "piper_runtime" / "piper" / "piper.exe"
FALLBACK_MODEL_PATH = _FALLBACK_ROOT / "ne_NP-google-x_low.onnx"
FALLBACK_CONFIG_PATH = _FALLBACK_ROOT / "ne_NP-google-x_low.onnx.json"
FALLBACK_HAZARD_WAV = _FALLBACK_ROOT / "phrase4.wav"


def resolve_piper_paths() -> Dict[str, Optional[Path]]:
    """Resolves operational paths for Piper executable, model, config, and pre-rendered hazard WAV."""
    exe_env = os.environ.get("TRINETRA_PIPER_EXE")
    model_env = os.environ.get("TRINETRA_PIPER_MODEL")
    config_env = os.environ.get("TRINETRA_PIPER_CONFIG")
    hazard_env = os.environ.get("TRINETRA_PIPER_HAZARD_WAV")

    exe_path = Path(exe_env) if exe_env else (DEFAULT_PIPER_EXE if DEFAULT_PIPER_EXE.is_file() else FALLBACK_PIPER_EXE)
    model_path = Path(model_env) if model_env else (DEFAULT_MODEL_PATH if DEFAULT_MODEL_PATH.is_file() else FALLBACK_MODEL_PATH)
    config_path = Path(config_env) if config_env else (DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.is_file() else FALLBACK_CONFIG_PATH)
    hazard_path = Path(hazard_env) if hazard_env else (DEFAULT_HAZARD_WAV if DEFAULT_HAZARD_WAV.is_file() else FALLBACK_HAZARD_WAV)

    return {
        "exe": exe_path if exe_path.is_file() else None,
        "model": model_path if model_path.is_file() else None,
        "config": config_path if config_path.is_file() else None,
        "hazard_wav": hazard_path if hazard_path.is_file() else None,
    }


def is_piper_available() -> bool:
    """Returns True if Piper executable and voice model files exist and Piper is not disabled."""
    if os.environ.get("TRINETRA_DISABLE_PIPER", "").lower() in ("1", "true", "yes"):
        return False
    paths = resolve_piper_paths()
    return paths["exe"] is not None and paths["model"] is not None


class PiperSpeechBackend(SpeechBackend):
    """
    High-performance, local neural TTS backend for Nepali using Piper Windows runtime.
    Maintains a single background worker process to eliminate cold ONNX load latency.
    Supports asynchronous audio playback via winsound, instant stop preemption (SND_PURGE),
    and safe temporary-file management with a bounded ring buffer.
    """

    def __init__(
        self,
        exe_path: Optional[Path] = None,
        model_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        hazard_wav: Optional[Path] = None,
        temp_dir: Optional[Path] = None,
    ):
        resolved = resolve_piper_paths()
        self.exe_path = exe_path or resolved["exe"]
        self.model_path = model_path or resolved["model"]
        self.config_path = config_path or resolved["config"]
        self.hazard_wav = hazard_wav or resolved["hazard_wav"]

        self._temp_dir = temp_dir or (Path(tempfile.gettempdir()) / "trinetra_piper")
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        self._worker_proc: Optional[subprocess.Popen] = None
        self._worker_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._synthesis_active = False

        self._current_playing_file: Optional[str] = None
        self._managed_files: List[Path] = []
        self._max_managed_files = 5
        self._files_lock = threading.Lock()
        self._speech_rate: float = 1.0

    def is_ready(self) -> bool:
        """Returns True if the backend has valid binary and model paths."""
        return (
            self.exe_path is not None
            and self.exe_path.is_file()
            and self.model_path is not None
            and self.model_path.is_file()
        )

    def _ensure_worker(self) -> bool:
        """Spawns or verifies the persistent piper.exe worker process."""
        with self._worker_lock:
            if self._worker_proc is not None and self._worker_proc.poll() is None:
                return True
            if not self.is_ready():
                logger.warning("PiperSpeechBackend cannot start worker: missing binary or model file.")
                return False

            cmd = [
                str(self.exe_path),
                "-m", str(self.model_path),
                "--json-input",
                "--output_dir", str(self._temp_dir),
            ]
            if self.config_path and self.config_path.is_file():
                cmd.extend(["-c", str(self.config_path)])

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                )
                self._worker_proc = proc
                logger.info(f"Persistent Piper worker spawned successfully (PID {proc.pid}).")
                return True
            except Exception as exc:
                logger.error(f"Failed to spawn Piper worker process: {exc}")
                self._worker_proc = None
                return False

    def _normalize_wav(self, wav_path: str, target_peak_ratio: float = 0.88) -> None:
        """
        Normalizes peak amplitude in 16-bit PCM WAV to prevent clipping and distortion.
        Safely scales samples if peak exceeds target threshold.
        """
        try:
            if not os.path.exists(wav_path):
                return
            with wave.open(wav_path, "rb") as wf:
                params = wf.getparams()
                if params.sampwidth != 2:
                    return
                frames = wf.readframes(params.nframes)
            
            samples = list(struct.unpack(f"<{params.nframes}h", frames))
            if not samples:
                return
            
            max_amp = max(abs(s) for s in samples)
            target_max = int(32767 * target_peak_ratio)
            if max_amp > target_max and max_amp > 0:
                scale = target_max / float(max_amp)
                samples = [int(s * scale) for s in samples]
                packed = struct.pack(f"<{len(samples)}h", *samples)
                with wave.open(wav_path, "wb") as wf:
                    wf.setparams(params)
                    wf.writeframes(packed)
        except Exception as exc:
            logger.debug(f"WAV normalization skipped on {wav_path}: {exc}")

    @property
    def speech_rate(self) -> float:
        return self._speech_rate

    @speech_rate.setter
    def speech_rate(self, value: float) -> None:
        self._speech_rate = max(0.5, min(2.5, float(value)))

    def speak(self, text: str, interrupt: bool = False, language: Optional[str] = None) -> bool:
        """
        Synthesizes and speaks text using Piper.
        Supports instant preemption, pre-rendered safety hazard fast-path, and safe file playback.
        """
        if interrupt:
            self.stop()

        clean_text = "".join(c for c in text if c.isalnum() or ("\u0900" <= c <= "\u097f") or c in " ,.!?'-_।").strip()
        if not clean_text:
            return False

        self._stop_event.clear()

        # Fast-path for canonical safety hazards: bypass neural synthesis entirely
        is_hazard = (
            "सावधान" in clean_text
            or clean_text == "सावधान! अगाडि अवरोध छ।"
        )
        if is_hazard and self.hazard_wav and self.hazard_wav.is_file():
            return self._play_wav(str(self.hazard_wav), is_managed=False)

        if not self._ensure_worker():
            return False

        # Neural synthesis via persistent piper.exe
        req_id = f"utt_{int(time.time() * 1000)}"
        output_target_path = str(self._temp_dir / f"{req_id}.wav")
        length_scale = round(1.0 / max(0.5, min(2.5, self._speech_rate)), 2)
        req_payload = json.dumps({
            "text": clean_text,
            "output_file": output_target_path,
            "length_scale": length_scale,
        }) + "\n"

        target_wav: Optional[str] = None
        with self._worker_lock:
            if self._stop_event.is_set():
                return False
            self._synthesis_active = True
            try:
                assert self._worker_proc is not None and self._worker_proc.stdin is not None
                self._worker_proc.stdin.write(req_payload)
                self._worker_proc.stdin.flush()
                line = self._worker_proc.stdout.readline()
                target_wav = line.strip() if line else output_target_path
            except Exception as exc:
                logger.warning(f"Piper synthesis communication error: {exc}")
                self._terminate_worker_unsafe()
                return False
            finally:
                self._synthesis_active = False

        if self._stop_event.is_set() or not target_wav:
            # Preempted during synthesis or synthesis error; discard
            if target_wav and os.path.exists(target_wav):
                try:
                    os.unlink(target_wav)
                except Exception:
                    pass
            elif os.path.exists(output_target_path):
                try:
                    os.unlink(output_target_path)
                except Exception:
                    pass
            return False

        full_wav_path = target_wav if os.path.isabs(target_wav) else os.path.join(str(self._temp_dir), target_wav)
        return self._play_wav(full_wav_path, is_managed=True)

    def _play_wav(self, wav_path: str, is_managed: bool = True) -> bool:
        """Plays a WAV file via winsound asynchronously and waits until completion or stop."""
        if not os.path.exists(wav_path):
            logger.warning(f"Audio file does not exist: {wav_path}")
            return False

        if self._stop_event.is_set():
            return False

        # Automatically normalize audio to prevent digital clipping / distortion
        self._normalize_wav(wav_path, target_peak_ratio=0.88)

        if is_managed:
            self._register_managed_file(Path(wav_path))

        file_size = os.path.getsize(wav_path)
        # 16000 Hz, 16-bit mono = 32000 bytes/sec; header is 44 bytes
        duration_s = max(0.1, (file_size - 44) / 32000.0) if file_size > 44 else 1.0

        if sys.platform == "win32":
            try:
                import winsound
                self._current_playing_file = wav_path
                winsound.PlaySound(wav_path, winsound.SND_ASYNC)
            except Exception as exc:
                logger.warning(f"winsound playback error: {exc}")
                self._current_playing_file = None
                return False
        else:
            # Non-Windows fallback (mock / test environment)
            self._current_playing_file = wav_path

        # Wait for audio playback duration or early interruption
        interrupted = self._stop_event.wait(timeout=duration_s)

        self._current_playing_file = None
        if interrupted:
            return False

        # Run bounded garbage collection for unmanaged/played slots
        self._cleanup_old_managed_files()
        return True

    def stop(self) -> None:
        """
        Immediately halts active playback, purges audio buffer, and aborts in-flight synthesis.
        """
        self._stop_event.set()

        # 1. Purge kernel sound playback immediately (< 100 ms)
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass

        # 2. If synthesis is active, terminate worker to unblock readline immediately
        with self._worker_lock:
            if self._synthesis_active and self._worker_proc and self._worker_proc.poll() is None:
                try:
                    self._worker_proc.terminate()
                except Exception:
                    pass
                self._worker_proc = None
                self._synthesis_active = False

    def _terminate_worker_unsafe(self) -> None:
        """Kills active worker without acquiring locks."""
        if self._worker_proc and self._worker_proc.poll() is None:
            try:
                self._worker_proc.kill()
            except Exception:
                pass
        self._worker_proc = None

    def _register_managed_file(self, path: Path) -> None:
        """Adds a newly created temporary audio file to tracked list."""
        with self._files_lock:
            self._managed_files.append(path)

    def _cleanup_old_managed_files(self) -> None:
        """Recycles finished files, strictly protecting the currently playing file."""
        with self._files_lock:
            current = self._current_playing_file
            remaining: List[Path] = []
            # Keep up to max_managed_files; delete excess older files
            while len(self._managed_files) > self._max_managed_files:
                candidate = self._managed_files.pop(0)
                if current and str(candidate.resolve()) == str(Path(current).resolve()):
                    # Never delete the active playing file!
                    remaining.append(candidate)
                    continue
                try:
                    if candidate.is_file():
                        candidate.unlink(missing_ok=True)
                except Exception:
                    pass
            self._managed_files = remaining + self._managed_files

    def get_available_voices(self) -> List[Dict[str, Any]]:
        if not self.is_ready():
            return []
        return [
            {
                "id": "piper-ne-google-x_low",
                "name": "Nepali (Google x_low)",
                "language": "ne-NP",
                "gender": "male",
            }
        ]

    def has_voice_for_language(self, lang: str) -> bool:
        norm = lang.strip().lower()
        return (norm == "ne" or norm.startswith("ne-")) and self.is_ready()

    def shutdown(self) -> None:
        """Gracefully halts audio and shuts down background worker process."""
        self.stop()
        with self._worker_lock:
            if self._worker_proc and self._worker_proc.poll() is None:
                try:
                    if self._worker_proc.stdin:
                        self._worker_proc.stdin.close()
                    self._worker_proc.wait(timeout=2.0)
                except Exception:
                    try:
                        self._worker_proc.kill()
                    except Exception:
                        pass
            self._worker_proc = None

        # Clean up temporary audio files on shutdown
        with self._files_lock:
            for f in self._managed_files:
                try:
                    if f.is_file():
                        f.unlink(missing_ok=True)
                except Exception:
                    pass
            self._managed_files.clear()


_DEFAULT_PIPER_SENTINEL = object()


class CompositeSpeechBackend(SpeechBackend):
    """
    Composite speech router providing unified bilingual speech synthesis:
    - English requests route to WindowsSapiSpeechBackend (instant WinRT synthesis, ~80ms).
    - Nepali requests route to PiperSpeechBackend (local neural synthesis via ne_NP model).
    - Zero silent fallback: If Nepali voice is requested and Piper is unavailable, speech is suppressed.
    """

    def __init__(
        self,
        sapi_backend: Optional[SpeechBackend] = None,
        piper_backend: Any = _DEFAULT_PIPER_SENTINEL,
    ):
        self.sapi_backend = sapi_backend or WindowsSapiSpeechBackend()
        if piper_backend is _DEFAULT_PIPER_SENTINEL:
            self.piper_backend = PiperSpeechBackend() if is_piper_available() else None
        else:
            self.piper_backend = piper_backend

    @property
    def speech_rate(self) -> float:
        return getattr(self, "_speech_rate", 1.0)

    @speech_rate.setter
    def speech_rate(self, value: float) -> None:
        self._speech_rate = max(0.5, min(2.5, float(value)))
        if hasattr(self.sapi_backend, "speech_rate"):
            self.sapi_backend.speech_rate = self._speech_rate
        if self.piper_backend and hasattr(self.piper_backend, "speech_rate"):
            self.piper_backend.speech_rate = self._speech_rate

    def speak(self, text: str, interrupt: bool = False, language: Optional[str] = None) -> bool:
        """Routes text to the appropriate backend based on explicit language or Devanagari Unicode detection."""
        lang = (language or "").strip().lower()
        has_devanagari = any("ऀ" <= c <= "ॿ" for c in text)
        has_latin = any(("a" <= c <= "z") or ("A" <= c <= "Z") for c in text)

        # If text is in Latin/English without Devanagari characters (e.g. "hello", "thank you"):
        # Route to English SAPI so it speaks natural English instead of garbling through Devanagari phonemizer.
        if has_latin and not has_devanagari:
            return self.sapi_backend.speak(text, interrupt=interrupt)

        is_nepali_lang = lang == "ne" or lang.startswith("ne-")
        if is_nepali_lang or has_devanagari:
            if self.piper_backend and self.piper_backend.has_voice_for_language("ne"):
                return self.piper_backend.speak(text, interrupt=interrupt, language=language)
            else:
                logger.warning(
                    "Nepali speech announcement suppressed: No verified Nepali TTS voice installed on system."
                )
                return False
        else:
            # Default: route English/Latin text to SAPI
            return self.sapi_backend.speak(text, interrupt=interrupt)

    def stop(self) -> None:
        """Stops active audio on both backends immediately."""
        self.sapi_backend.stop()
        if self.piper_backend:
            self.piper_backend.stop()

    def get_available_voices(self) -> List[Dict[str, Any]]:
        voices = list(self.sapi_backend.get_available_voices())
        if self.piper_backend:
            voices.extend(self.piper_backend.get_available_voices())
        return voices

    def has_voice_for_language(self, lang: str) -> bool:
        norm = lang.strip().lower()
        if norm == "ne" or norm.startswith("ne-"):
            return self.piper_backend is not None and self.piper_backend.has_voice_for_language(lang)
        return self.sapi_backend.has_voice_for_language(lang)

    def shutdown(self) -> None:
        self.sapi_backend.shutdown()
        if self.piper_backend:
            self.piper_backend.shutdown()
