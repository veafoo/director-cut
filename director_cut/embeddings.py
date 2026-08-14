import numpy as np
import torch

_inference = None


def _device():
    # GPU NVIDIA si dispo, sinon CPU (on évite MPS, source de bugs sur Mac
    # pour ce modèle ; l'empreinte est courte, le CPU suffit largement).
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _get_inference():
    """Charge (une fois) le modèle d'empreinte vocale pyannote/wespeaker."""
    global _inference
    if _inference is None:
        from pyannote.audio import Inference, Model
        try:
            model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM")
        except TypeError:
            model = Model.from_pretrained(
                "pyannote/wespeaker-voxceleb-resnet34-LM", use_auth_token=True)
        inf = Inference(model, window="whole")
        try:
            inf.to(_device())
        except Exception:
            inf.to(torch.device("cpu"))
        _inference = inf
    return _inference


def _normalize(vec):
    vec = np.asarray(vec, dtype=np.float32).reshape(-1)
    return vec / (np.linalg.norm(vec) + 1e-9)


def embed_array(wav, sr=16000):
    """Empreinte d'un extrait audio en mémoire (numpy 1D)."""
    x = np.asarray(wav, dtype=np.float32).reshape(1, -1)  # (channel=1, samples)
    waveform = torch.from_numpy(x)
    out = _get_inference()({"waveform": waveform, "sample_rate": int(sr)})
    return _normalize(out)


def embed_file(path):
    """Empreinte d'un fichier audio (mono, rééchantillonné à 16 kHz)."""
    import soundfile as sf
    wav, sr = sf.read(path)
    wav = np.asarray(wav, dtype=np.float32)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != 16000:
        import torchaudio
        wav = torchaudio.functional.resample(
            torch.from_numpy(wav), sr, 16000).numpy()
        sr = 16000
    return embed_array(wav, sr)


def cosine(a, b):
    return float(np.dot(a, b))
