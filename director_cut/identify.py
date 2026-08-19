from collections import defaultdict

import numpy as np
import soundfile as sf

from .embeddings import cosine, embed_array


def load_reference(ref_path):
    """Charge (ref, threshold). .npz = empreinte calibrée ; .npy = legacy."""
    data = np.load(ref_path, allow_pickle=False)
    if hasattr(data, "files"):  # NpzFile
        ref = data["ref"]
        thr = float(data["threshold"]) if "threshold" in data.files else None
        return np.asarray(ref), thr
    return np.asarray(data), None


def _load_wav(path):
    wav, sr = sf.read(path)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return np.asarray(wav, dtype=np.float32), sr


MIN_VERIF = 1.0     # sous cette durée, une empreinte ne veut plus rien dire


def verify_turns(wav_path, segs, ref_path, threshold, min_dur=MIN_VERIF):
    """Revérifie un à un les tours attribués à sa voix.

    Le regroupement de la diarisation n'est pas infaillible : sur un JT réel,
    une voix off de publicité s'est retrouvée dans son groupe. Le groupe entier
    passait quand même le seuil (sa moyenne restait bonne), mais ce fragment
    étranger prolongeait son passage au-delà du retour plateau — et toute la
    suite de la découpe s'en trouvait faussée.

    On garde donc un tour s'il ressemble à SON empreinte, pas seulement à celle
    du groupe. Les tours trop courts pour être jugés sont conservés : sur moins
    d'une seconde, une empreinte est du bruit.

    Renvoie (gardés, écartés)."""
    ref, _ = load_reference(ref_path)
    wav, sr = _load_wav(wav_path)
    gardes, ecartes = [], []
    for s, e in segs:
        if e - s < min_dur:
            gardes.append((s, e))
            continue
        a, b = int(s * sr), int(e * sr)
        if b <= a:
            continue
        score = cosine(embed_array(wav[a:b], sr), ref)
        (gardes if score >= threshold else ecartes).append((s, e))
    return gardes, ecartes


def find_her_segments(wav_path, turns, ref_path, threshold=None,
                      max_enroll_sec=60):
    """Compare chaque locuteur à l'empreinte. Si threshold None -> seuil calibré
    stocké dans l'empreinte. `turns` = liste [(debut, fin, label), ...].
    Renvoie (label, scores, segments, seuil_utilisé)."""
    ref, stored_thr = load_reference(ref_path)
    if threshold is None:
        threshold = stored_thr if stored_thr is not None else 0.25

    wav, sr = _load_wav(wav_path)
    by_label = defaultdict(list)
    for s, e, label in turns:
        by_label[label].append((s, e))

    scores = {}
    for label, segs in by_label.items():
        chunks, total = [], 0.0
        for s, e in sorted(segs):
            if total >= max_enroll_sec:
                break
            a, b = int(s * sr), int(e * sr)
            if b > a:
                chunks.append(wav[a:b])
                total += (e - s)
        if not chunks:
            continue
        emb = embed_array(np.concatenate(chunks), sr)
        scores[label] = cosine(emb, ref)

    if not scores:
        return None, {}, [], threshold
    best = max(scores, key=scores.get)
    if scores[best] < threshold:
        return None, scores, [], threshold
    return best, scores, sorted(by_label[best]), threshold
