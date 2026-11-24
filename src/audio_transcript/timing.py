"""Per-attempt monotonic timing and conservative transcription-only estimates.

The worker owns the mutable calculator. Immutable snapshots cross the Qt thread
boundary; the UI can read them on its own clock without worker callbacks.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from time import monotonic


def positive(value: float | None) -> float | None:
    return value if value is not None and isfinite(value) and value > 0 else None


@dataclass(frozen=True, slots=True)
class TimingView:
    elapsed: float
    speed: float | None
    remaining: float | None
    eta_state: str


@dataclass(frozen=True, slots=True)
class TimingSnapshot:
    started_at: float
    finished_at: float | None
    phase: str
    inference_started_at: float | None
    processed: float
    duration: float | None
    last_progress_at: float | None
    stale_after: float
    smoothed_speed: float | None

    def view(self, now: float) -> TimingView:
        elapsed = max(0.0, (self.finished_at if self.finished_at is not None else now) - self.started_at)
        active = self.finished_at is None and self.phase == "Transcribing"
        reference = self.last_progress_at if self.last_progress_at is not None else self.inference_started_at
        stale = reference is not None and now - reference > self.stale_after
        inference = max(0.0, now - self.inference_started_at) if self.inference_started_at is not None else 0.0
        speed = positive(self.processed / inference) if active and not stale and inference > 0 else None
        state = "estimating" if active and self.duration and not stale else "unavailable"
        remaining = None
        if state == "estimating" and self.smoothed_speed and speed:
            # No countdown from unobserved media progress. During long inference
            # gaps cap optimism by the actual cumulative rate, then expire entirely.
            remaining = max(0.0, self.duration - self.processed) / min(self.smoothed_speed, speed)
            state = "available"
        return TimingView(elapsed, speed, remaining, state)


class AttemptTiming:
    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self.clock = clock
        self.started_at = clock()
        self.finished_at: float | None = None
        self.phase = "Preparing"
        self.inference_started_at: float | None = None
        self.processed = 0.0
        self.duration: float | None = None
        self.last_progress_at: float | None = None
        self.stale_after = 30.0
        self.smoothed_speed: float | None = None
        self._sample_at: float | None = None
        self._observations = 0

    def set_phase(self, phase: str, *, duration: float | None = None) -> None:
        if self.finished_at is not None:
            return
        if phase == "Transcribing" and self.phase != phase:
            self.inference_started_at = self.clock()
            self._sample_at = self.inference_started_at
            self.duration = positive(duration)
        self.phase = phase

    def _invalidate(self, now: float) -> None:
        self.smoothed_speed = None
        self._observations = 0
        self._sample_at = now

    def observe(self, processed: float, duration: float | None) -> None:
        if self.finished_at is not None or self.phase != "Transcribing":
            return
        now = self.clock()
        valid_duration = positive(duration)
        if (not isfinite(processed) or processed <= self.processed
                or (valid_duration is not None and processed > valid_duration)):
            self._invalidate(now)
            return
        if self.last_progress_at is not None and now - self.last_progress_at > self.stale_after:
            self._invalidate(now)
        if valid_duration != self.duration:
            self._invalidate(now)
        self.duration = valid_duration
        self.processed = processed
        self.last_progress_at = now
        interval = now - self._sample_at if self._sample_at is not None else 0.0
        # Coalesce burst-delivered segments from the same inference window.
        if interval < 1.0:
            return
        self.stale_after = max(30.0, min(120.0, interval * 3))
        self._observations += 1
        inference = now - self.inference_started_at if self.inference_started_at is not None else 0.0
        if self._observations >= 3 and inference >= 5 and self.processed >= 5:
            rate = positive(self.processed / inference)
            if rate is not None:
                if self.smoothed_speed is None:
                    self.smoothed_speed = rate
                else:
                    smoothed = 0.75 * self.smoothed_speed + 0.25 * rate
                    self.smoothed_speed = min(self.smoothed_speed * 1.25, max(self.smoothed_speed * 0.75, smoothed))
        self._sample_at = now

    def finish(self, phase: str) -> None:
        if self.finished_at is None:
            self.finished_at = self.clock()
            self.phase = phase
            self.smoothed_speed = None

    def snapshot(self) -> TimingSnapshot:
        return TimingSnapshot(
            self.started_at, self.finished_at, self.phase, self.inference_started_at,
            self.processed, self.duration, self.last_progress_at, self.stale_after,
            self.smoothed_speed,
        )
