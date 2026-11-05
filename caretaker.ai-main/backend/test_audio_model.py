import sys
import os
import numpy as np

# Add the backend directory to sys.path so we can import services
sys.path.append(os.getcwd())

from services.audio_detection import AudioDetectionService

def test_audio_service():
    print("--- Initializing Audio Service ---")
    service = AudioDetectionService()

    if service.model_loaded:
        print("[OK] Success: Deep Learning Model Loaded correctly.")
    else:
        print("[FAIL] Failure: Deep Learning Model failed to load (running in acoustic-only mode).")

    print("\n--- Testing with Silence (Zeros) ---")
    # Generate 0.5 seconds of silence at 16kHz
    silence = np.zeros(int(16000 * 0.5), dtype=np.float32)
    silence_bytes = silence.tobytes()
    
    result_silence = service.process_audio_chunk(silence_bytes)
    print("Silence Result:", result_silence)

    print("\n--- Testing with Synthetic Sine Wave (should trigger acoustic features) ---")
    # Generate a loud 1kHz sine wave
    duration = 0.5
    fs = 16000
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    # create a sine wave
    sine_wave = 0.5 * np.sin(2 * np.pi * 1000 * t)
    sine_bytes = sine_wave.astype(np.float32).tobytes()

    result_sine = service.process_audio_chunk(sine_bytes)
    print("Sine Wave Result:", result_sine)
    
    # Ideally, a sine wave might be classified as 'Noise' or have low confidence for cough/sneeze
    # But this proves the pipeline runs end-to-end without crashing.

if __name__ == "__main__":
    test_audio_service()
