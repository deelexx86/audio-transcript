"""Pinned model packages and their desktop inference capabilities."""
from dataclasses import dataclass
from pathlib import PurePosixPath

from audio_transcript.acceleration import ExecutionMode
from audio_transcript.profiles import PROFILES


@dataclass(frozen=True, slots=True)
class CheckpointFile:
    path: str
    size: int
    sha256: str = ""

    @property
    def name(self) -> str:
        return PurePosixPath(self.path).name


@dataclass(frozen=True, slots=True)
class CatalogModel:
    key: str
    display_name: str
    directory_name: str
    upstream: str
    license: str
    repository: str
    revision: str
    precision: str
    files: tuple[CheckpointFile, ...]
    family: str = ""
    speakers: bool = False
    timestamps: bool = False
    streamed: bool = False
    limit: int | None = None
    options: tuple[str, ...] = ()

    @property
    def artifact_name(self) -> str:
        return self.directory_name

    @property
    def modes(self) -> tuple[ExecutionMode, ...]:
        if self.family:
            return (ExecutionMode.REMOTE_CUDA,)
        return tuple(ExecutionMode)


def whisper(profile, upstream, repository, revision, sizes, digest):
    names = ("config.json", "model.bin", "tokenizer.json", "vocabulary.json", "preprocessor_config.json")
    return CatalogModel(
        profile.key, profile.display_name.split(" — ", 1)[1], profile.directory_name, upstream, "MIT", repository,
        revision, "CUDA float16 / CPU int8",
        tuple(CheckpointFile(name, size, digest if name == "model.bin" else "") for name, size in zip(names, sizes)),
    )


GGUF_REPO = "audio-cpp/audio.cpp-gguf"
GGUF_REVISION = "047ec541cc3f7e50c583acd56e0177ae286c4078"


def gguf(key, name, upstream, license_name, family, filename, size, digest, precision,
         *, repository=GGUF_REPO, revision=GGUF_REVISION, extra=(), **capabilities):
    return CatalogModel(
        key, name, key, upstream, license_name, repository, revision, precision,
        (CheckpointFile(filename, size, digest), *extra), family, **capabilities,
    )


CATALOG = (
    whisper(PROFILES[0], "openai/whisper-large-v3", "Systran/faster-whisper-large-v3",
            "edaa852ec7e145841d8ffdb056a99866b5f0a478", (2394, 3087284237, 2480617, 1068114, 340),
            "69f74147e3334731bc3a76048733325d2ec74642fb52620eda87352e3d4f1"),
    whisper(PROFILES[1], "openai/whisper-large-v3-turbo", "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
            "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf", (2263, 1617884929, 2710337, 1068114, 340),
            "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da"),
    gguf("qwen3-asr-0.6b", "Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-0.6B", "Apache-2.0", "qwen3_asr",
         "Qwen3-ASR-0.6B-GGUF/qwen3-asr-0.6b-q8_0.gguf", 1151279968,
         "5c53bbb9a6b2ade85c16c290c560658ca18b78a23c323378528f1f945683fcbe", "Q8_0"),
    gguf("qwen3-asr-1.7b", "Qwen3-ASR-1.7B", "Qwen/Qwen3-ASR-1.7B", "Apache-2.0", "qwen3_asr",
         "Qwen3-ASR-1.7B-GGUF/qwen3-asr-1.7b-q8_0.gguf", 2473017600,
         "3bc2462eca3a3a8f56abcd860d0943ffdc0546547dde55a9d08589607d6f3936", "Q8_0"),
    gguf("gigaam-v3-e2e-rnnt", "GigaAM-v3 E2E RNNT", "ai-sage/GigaAM-v3 (e2e_rnnt)", "MIT", "gigaam_asr",
         "GigaAM-ASR-GGUF/gigaam-v3-e2e-rnnt-f16.gguf", 449056064,
         "e226e58e8815918fe074bcaf0499b26d5f9028b1291ded192cfad0ef2eb6689a", "F16"),
    gguf("gigaam-multilingual-large", "GigaAM Multilingual Large", "ai-sage/GigaAM-Multilingual (large_ctc)", "MIT", "gigaam_asr",
         "GigaAM-ASR-GGUF/gigaam-multilingual-large-ctc-f16.gguf", 1172282848,
         "39d1d2235fdd68cd25876e8e6392e93eae2f85578dae5a5aa59706c810a17c09", "F16"),
    gguf("parakeet-tdt-v3", "NVIDIA Parakeet TDT 0.6B v3", "nvidia/parakeet-tdt-0.6b-v3", "CC BY 4.0", "parakeet_tdt",
         "Parakeet-TDT-0.6B-v3-GGUF/parakeet-tdt-0.6b-v3-q8_0.gguf", 915735760,
         "6fa498f10f8cb606f041aa9512733cfee842a932359b00b0c45b9b723c4f4f4b", "Q8_0",
         options=("--session-option", "parakeet_tdt.offline_mode=auto",
                  "--session-option", "parakeet_tdt.audio_chunk_duration_sec=15")),
    gguf("vibevoice-asr", "Microsoft VibeVoice-ASR", "microsoft/VibeVoice-ASR", "MIT", "vibevoice_asr",
         "VibeVoice-ASR-GGUF/vibevoice-asr-q8_0.gguf", 9858648480,
         "6cefa920277f13d102c0014397044c52b63aa02e1a54f519e1732e04217859f8", "Q8_0",
         speakers=True, timestamps=True, limit=3600, options=("--audio-chunk-mode", "none")),
    gguf("vibevoice-streaming-1.5b", "Microsoft VibeVoice-ASR-Streaming-1.5B", "microsoft/VibeVoice-ASR-Streaming-1.5B",
         "MIT", "vibevoice_asr_streaming", "vibevoice-asr-streaming-1.5b-q8_0.gguf", 3343199488,
         "1a92c0f6c72439d58dedaaff96bb77264802618bd577f58cc0176f47bae5180d", "Q8_0",
         repository="christopherthompson81/VibeVoice-ASR-Streaming-1.5B-GGUF",
         revision="ff96151102990984d6d0e951e62751bdb2ff9243", speakers=True, streamed=True, limit=3600),
    gguf("vibevoice-streaming-7b", "Microsoft VibeVoice-ASR-Streaming-7B", "microsoft/VibeVoice-ASR-Streaming-7B",
         "MIT", "vibevoice_asr_streaming", "VibeVoice-ASR-Streaming-7B-GGUF/vibevoice-asr-streaming-7b-q4_k.gguf",
         5859086656, "4d9b83a02242d45146c44054cd46ed2e84e1cf75c4487b0af8604587d8421568", "Q4_K",
         speakers=True, streamed=True, limit=3600),
    gguf("moss-transcribe-diarize", "MOSS-Transcribe-Diarize 0.9B", "OpenMOSS-Team/MOSS-Transcribe-Diarize",
         "Apache-2.0", "moss_transcribe_diarize", "MOSS-Transcribe-Diarize-GGUF/moss-transcribe-diarize-bf16.gguf",
         1833018080, "5bc627289e2586fc2d9269afda15a305e545a4ff3512c902889be71d58e56ad5", "BF16",
         speakers=True, timestamps=True, limit=3600),
    gguf("nemotron-transcribe", "NVIDIA Nemotron 3.5 Transcribe 30B-A4B",
         "nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B", "OpenMDW-1.1", "nemotron_transcribe",
         "nemotron-transcribe-30b-a4b-experts-Q2_K.gguf", 13946026784,
         "c8a631a85cf1f91943259976a6aab560f56de2fe50667836a92c217b2af04567", "Q2_K experts / Q8_0 dense / F16 encoder",
         repository="Jmica/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-GGUF",
         revision="d2affa8419718ffe0917cb69dc6bc693084497f5",
         extra=(CheckpointFile("mmproj-NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-Encoder-F16.gguf",
                               1670410080, "4221029c8a565c4a80c507ffa760c716e595acf663f9f4273ce69910050e7ba2"),),
         speakers=True, timestamps=True, limit=3600,
         options=("--session-option", "moe_disk_experts=true",
                  "--session-option", "moe_disk_expert_read_threads=1",
                  "--session-option", "moe_expert_cache_size=32",
                  "--request-option", "diarization=true")),
)

CATALOG_BY_KEY = {model.key: model for model in CATALOG}
