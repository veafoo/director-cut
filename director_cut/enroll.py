import os
from collections import defaultdict

import numpy as np
import soundfile as sf

from .audio import extract_wav
from .embeddings import embed_array


def _load_wav(path):
    wav, sr = sf.read(path)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return np.asarray(wav, dtype=np.float32), sr


def _windows(wav, sr, segs, win=4.0, hop=4.0, min_win=1.5):
    """Découpe des segments (start,end) en fenêtres de ~win s."""
    out = []
    for s, e in segs:
        t = s
        while t < e:
            a, b = int(t * sr), int(min(e, t + win) * sr)
            if (b - a) / sr >= min_win:
                out.append(wav[a:b])
            t += hop
    return out


def _embed_all(windows, sr):
    return [embed_array(w, sr) for w in windows]


def _dominant_label(turns):
    dur = defaultdict(float)
    for s, e, lab in turns:
        dur[lab] += e - s
    label = max(dur, key=dur.get)
    return label, dict(dur)


def calibrate_threshold(self_sims, other_sims):
    """Seuil auto : posé entre la distribution de SA voix et celle des autres."""
    self_sims = sorted(float(x) for x in self_sims)
    if other_sims:
        lo = float(np.percentile(self_sims, 10))   # bas de sa distribution
        hi = float(np.percentile(other_sims, 90))  # haut des autres voix
        thr = (lo + hi) / 2.0 if hi < lo else lo - 0.02
    else:
        m, sd = float(np.mean(self_sims)), float(np.std(self_sims))
        thr = m - 2.0 * sd
    return float(min(0.45, max(0.18, thr)))


def _save(out_path, ref, threshold, meta=None):
    if not out_path.endswith(".npz"):
        out_path += ".npz"
    np.savez(out_path, ref=ref.astype(np.float32),
             threshold=np.float32(threshold))
    return out_path


def enroll_from_chronique(sample_path, out_path, hf_token, diarize_fn,
                          workdir="."):
    """Empreinte AUTO depuis une chronique brute (plusieurs voix) :
    diarise, retient le locuteur dominant (= elle), calibre le seuil."""
    wav_path = os.path.join(workdir, "_enroll.wav")
    extract_wav(sample_path, wav_path)
    try:
        turns = diarize_fn(wav_path, hf_token, None)
        label, dur = _dominant_label(turns)
        wav, sr = _load_wav(wav_path)

        her_segs, other_segs = [], []
        for s, e, lab in turns:
            (her_segs if lab == label else other_segs).append((s, e))

        her_w = _embed_all(_windows(wav, sr, her_segs), sr)
        if not her_w:
            raise RuntimeError("Pas assez de voix exploitable dans le sample.")
        ref = np.mean(her_w, axis=0)
        ref = ref / (np.linalg.norm(ref) + 1e-9)

        self_sims = [float(np.dot(w, ref)) for w in her_w]
        other_w = _embed_all(_windows(wav, sr, other_segs), sr) if other_segs else []
        other_sims = [float(np.dot(w, ref)) for w in other_w]
        thr = calibrate_threshold(self_sims, other_sims)

        saved = _save(out_path, ref, thr)
        return saved, thr, dur[label], len(other_w)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass


def enroll_from_clean_samples(sample_paths, out_path):
    """Empreinte depuis des extraits déjà propres (sa voix seule).
    Calibration sans 'autres voix' -> seuil dérivé de sa variabilité."""
    from .embeddings import embed_file
    embs = []
    for p in sample_paths:
        wav_path = p
        tmp = None
        if not p.lower().endswith((".wav", ".flac")):
            tmp = p + ".enroll.wav"
            extract_wav(p, tmp)
            wav_path = tmp
        wav, sr = _load_wav(wav_path)
        embs.extend(_embed_all(_windows(wav, sr, [(0, len(wav) / sr)]), sr))
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
    ref = np.mean(embs, axis=0)
    ref = ref / (np.linalg.norm(ref) + 1e-9)
    self_sims = [float(np.dot(w, ref)) for w in embs]
    thr = calibrate_threshold(self_sims, [])
    return _save(out_path, ref, thr), thr, len(embs)
