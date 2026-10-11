import math

import pytest

from audio_transcript.timing import AttemptTiming


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def warmed(duration=120):
    clock = Clock()
    timing = AttemptTiming(clock=clock)
    timing.set_phase("Transcribing", duration=duration)
    for position in (10, 20, 30):
        clock.advance(5)
        timing.observe(position, duration)
    return clock, timing


def test_elapsed_without_callbacks_and_opaque_phases():
    clock = Clock()
    timing = AttemptTiming(clock=clock)
    for phase in ("Preparing", "Downloading", "Waiting to retry", "Preparing", "Saving"):
        timing.set_phase(phase)
        clock.advance(7)
        view = timing.snapshot().view(clock())
        assert view.elapsed == clock() - 100
        assert view.remaining is None and view.speed is None
        assert view.eta_state == "unavailable"


def test_initial_evidence_and_normal_eta_exclude_preparation():
    clock = Clock()
    timing = AttemptTiming(clock=clock)
    clock.advance(200)
    timing.set_phase("Transcribing", duration=120)
    assert timing.snapshot().view(clock()).eta_state == "estimating"
    for position in (10, 20):
        clock.advance(5)
        timing.observe(position, 120)
        assert timing.snapshot().view(clock()).remaining is None
    clock.advance(5)
    timing.observe(30, 120)
    view = timing.snapshot().view(clock())
    assert view.elapsed == 215
    assert view.speed == 2
    assert view.remaining == 45


def test_smoothing_and_burst_segments_do_not_create_large_jumps():
    clock, timing = warmed(600)
    previous = timing.snapshot().view(clock()).remaining
    clock.advance(5)
    timing.observe(200, 600)
    view = timing.snapshot().view(clock())
    assert previous * 0.5 < view.remaining < previous
    # Multiple segments yielded from one inference window are not independent samples.
    timing.observe(201, 600)
    assert view.remaining - 1 < timing.snapshot().view(clock()).remaining <= view.remaining


@pytest.mark.parametrize("position", [0, -1, 29, 121, math.nan, math.inf])
def test_unreliable_observations_invalidate_eta(position):
    clock, timing = warmed()
    clock.advance(5)
    timing.observe(position, 120)
    assert timing.snapshot().view(clock()).remaining is None


def test_stalled_progress_and_recovery_need_fresh_evidence():
    clock, timing = warmed()
    snapshot = timing.snapshot()
    clock.advance(31)
    view = snapshot.view(clock())
    assert view.eta_state == "unavailable"
    assert view.speed is None
    assert view.elapsed == 46
    timing.observe(40, 120)
    assert timing.snapshot().view(clock()).remaining is None
    for position in (50, 60, 70):
        clock.advance(5)
        timing.observe(position, 120)
    assert timing.snapshot().view(clock()).remaining is not None


@pytest.mark.parametrize("duration", [None, 0, -1, math.nan, math.inf])
def test_unknown_duration_never_fabricates_eta(duration):
    clock, timing = warmed(duration)
    view = timing.snapshot().view(clock())
    assert view.remaining is None and view.eta_state == "unavailable"
    assert view.speed == 2


def test_zero_time_does_not_produce_infinite_throughput():
    clock = Clock()
    timing = AttemptTiming(clock=clock)
    timing.set_phase("Transcribing", duration=120)
    timing.observe(10, 120)
    assert timing.snapshot().view(clock()).speed is None
    assert timing.snapshot().view(clock()).remaining is None


@pytest.mark.parametrize("terminal", ["Done", "Error", "Cancelled"])
def test_terminal_elapsed_frozen_and_retry_and_batch_are_independent(terminal):
    clock, timing = warmed()
    timing.set_phase("Saving")
    clock.advance(4)
    timing.finish(terminal)
    clock.advance(100)
    view = timing.snapshot().view(clock())
    assert view.elapsed == 19
    assert view.remaining is None and view.speed is None
    fresh = AttemptTiming(clock=clock)
    assert fresh.snapshot().view(clock()).elapsed == 0
    fresh.set_phase("Transcribing", duration=300)
    assert fresh.snapshot().view(clock()).remaining is None
    assert timing.snapshot().view(clock()).elapsed == 19
