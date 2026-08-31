from audio_transcript.bootstrap_models import build_parser


def test_bootstrap_cli_defaults_to_both_profiles() -> None:
    assert build_parser().parse_args([]).profiles == []


def test_bootstrap_cli_accepts_profile_subset() -> None:
    assert build_parser().parse_args(["fast"]).profiles == ["fast"]
