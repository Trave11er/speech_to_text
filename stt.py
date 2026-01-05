import os
import signal
import subprocess as sp
import sys

import numpy as np
import onnxruntime as ort
import sherpa_onnx
import sounddevice as sd

SAMPLE_RATE = 16000
VAD_THRESHOLD = 0.5
CHUNK_SAMPLES = 512  # 32ms at 16kHz

# sherpa-onnx model files (Transducer / NeMo Parakeet style)
# You can override these via env vars:
#   SHERPA_ENCODER, SHERPA_DECODER, SHERPA_JOINER, SHERPA_TOKENS
SHERPA_MODEL_DIR = os.environ.get(
    "SHERPA_MODEL_DIR",
    os.path.join(
        os.path.dirname(__file__), "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
    ),
)
SHERPA_ENCODER = os.environ.get(
    "SHERPA_ENCODER", os.path.join(SHERPA_MODEL_DIR, "encoder.int8.onnx")
)
SHERPA_DECODER = os.environ.get(
    "SHERPA_DECODER", os.path.join(SHERPA_MODEL_DIR, "decoder.int8.onnx")
)
SHERPA_JOINER = os.environ.get(
    "SHERPA_JOINER", os.path.join(SHERPA_MODEL_DIR, "joiner.int8.onnx")
)
SHERPA_TOKENS = os.environ.get(
    "SHERPA_TOKENS", os.path.join(SHERPA_MODEL_DIR, "tokens.txt")
)

def get_recognizer():
    """Create recognizer from model files."""
    missing = [
        p
        for p in [SHERPA_ENCODER, SHERPA_DECODER, SHERPA_JOINER, SHERPA_TOKENS]
        if not os.path.exists(p)
    ]
    if missing:
        print("Missing sherpa-onnx model files:")
        for p in missing:
            print(f"  {p}")
        print(
            "Set SHERPA_MODEL_DIR or SHERPA_ENCODER/SHERPA_DECODER/SHERPA_JOINER/SHERPA_TOKENS env vars."
        )
        return None

    return sherpa_onnx.OfflineRecognizer.from_transducer(
        SHERPA_ENCODER,
        SHERPA_DECODER,
        SHERPA_JOINER,
        SHERPA_TOKENS,
        num_threads=8,
        provider="cpu",
        debug=False,
        decoding_method="greedy_search",
        model_type="nemo_transducer",
    )


# Load Silero VAD v4 ONNX
VAD_PATH = os.path.join(os.path.dirname(__file__), "silero_vad_v4.onnx")
vad_session = ort.InferenceSession(VAD_PATH)


def vad_reset_state():
    return (
        np.zeros((2, 1, 64), dtype=np.float32),
        np.zeros((2, 1, 64), dtype=np.float32),
    )


recorded_frames = []
recording_state = "idle"  # idle, recording


def handle_signal(signum, frame):
    global recording_state
    if recording_state == "idle":
        recording_state = "start"
    elif recording_state == "recording":
        recording_state = "stop"


def handle_quit(signum, frame):
    print("\nExiting...")
    sys.exit(0)


def type_at_cursor(text):
    if not text or not text.strip():
        print("Empty transcription")
        return
    try:
        sp.run(["xdotool", "type", "--clearmodifiers", text + " "], check=True)
    except Exception as e:
        print(f"xdotool error: {e}")


def audio_callback(indata, frames, time_info, status):
    recorded_frames.append(indata.copy())


def filter_silence(audio):
    """Extract speech segments using Silero VAD v4"""
    vad_h, vad_c = vad_reset_state()
    speech_chunks = []
    sr = np.array(SAMPLE_RATE, dtype=np.int64)

    for i in range(0, len(audio), CHUNK_SAMPLES):
        chunk = audio[i : i + CHUNK_SAMPLES]
        if len(chunk) < CHUNK_SAMPLES:
            chunk = np.pad(chunk, (0, CHUNK_SAMPLES - len(chunk)))

        input_audio = chunk.reshape(1, -1).astype(np.float32)
        out, vad_h, vad_c = vad_session.run(
            None, {"input": input_audio, "h": vad_h, "c": vad_c, "sr": sr}
        )
        prob = out[0]

        if prob > VAD_THRESHOLD:
            speech_chunks.append(audio[i : i + CHUNK_SAMPLES])

    if not speech_chunks:
        return np.array([], dtype=np.float32)

    return np.concatenate(speech_chunks)


def main():
    global recording_state, recorded_frames

    # init recognizer first
    print("Loading recognizer...")
    recognizer = get_recognizer()
    if recognizer is None:
        return

    signal.signal(signal.SIGUSR1, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_quit)
    print(f"PID: {os.getpid()} - Ctrl+C/SIGUSR1 toggle, SIGTERM quit")

    while True:
        print("Waiting... (Ctrl+C to start recording)")
        recording_state = "idle"

        # wait for start signal
        while recording_state == "idle":
            sd.sleep(50)

        # record with mic open only during recording
        recorded_frames = []
        recording_state = "recording"
        print("\nRecording... (Ctrl+C to stop)")

        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=audio_callback
        ):
            while recording_state == "recording":
                sd.sleep(50)

        print("\nStopped, mic closed")

        if not recorded_frames:
            print("No audio recorded")
            continue

        audio = np.concatenate(recorded_frames).flatten()
        print(f"Recorded {len(audio) / SAMPLE_RATE:.1f}s, filtering silence...")

        audio = filter_silence(audio)
        if len(audio) == 0:
            print("No speech detected")
            continue

        print(f"Speech: {len(audio) / SAMPLE_RATE:.1f}s, transcribing...")
        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, audio.astype(np.float32, copy=False))
        recognizer.decode_stream(stream)
        text = (stream.result.text or "").strip()

        print(f"Result: {text}")
        type_at_cursor(text)


if __name__ == "__main__":
    main()
