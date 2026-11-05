# NOTE: do not import .architecture here — it imports TensorFlow, which must not
# be loaded in the API server process (it crashes alongside PyTorch/YOLO).
# Import it explicitly where needed:  from utils.audio_model.architecture import build_model
from .preprocessing import preprocess_chunk, audio_to_mel_spectrogram

CLASS_LABELS = ['Cough', 'Sneeze', 'Talking', 'Noise']
