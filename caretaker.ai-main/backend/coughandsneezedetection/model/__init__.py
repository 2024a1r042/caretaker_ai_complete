from .architecture import build_model
from .preprocessing import preprocess_chunk, audio_to_mel_spectrogram

CLASS_LABELS = ['Cough', 'Sneeze', 'Talking', 'Noise']
