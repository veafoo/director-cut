_models = {}


def load_model(model_size="small"):
    """Charge le modèle de transcription, une fois par taille demandée.

    Comme la diarisation, il ne dépend pas de la vidéo : sur un lot, un seul
    chargement suffit."""
    if model_size not in _models:
        from faster_whisper import WhisperModel
        _models[model_size] = WhisperModel(model_size, device="auto",
                                           compute_type="auto")
    return _models[model_size]


def transcribe_all(wav_path, model=None, model_size="small", lang="fr",
                   task="transcribe", on_progress=None):
    """task='transcribe' (langue d'origine) ou 'translate' (vers l'anglais).
    Renvoie [(debut, fin, texte), ...]."""
    m = model or load_model(model_size)
    kwargs = {"task": task, "vad_filter": True}
    if task == "transcribe":
        kwargs["language"] = lang
    segs, info = m.transcribe(wav_path, **kwargs)
    total = getattr(info, "duration", 0.0) or 0.0
    out = []
    for s in segs:
        out.append((s.start, s.end, s.text.strip()))
        if on_progress and total:
            on_progress(min(s.end, total), total)
    return out


def _srt_time(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def clip_srt(transcript, clip_start, clip_end, out_srt):
    """Écrit un .srt pour UN passage : segments chevauchant [clip_start,
    clip_end], recalés pour démarrer à 0 (le mp4 du passage démarre à 0)."""
    lines, idx = [], 1
    for ts, te, tx in transcript:
        if te > clip_start and ts < clip_end and tx:
            a = max(0.0, ts - clip_start)
            b = max(a + 0.1, te - clip_start)
            lines += [str(idx), f"{_srt_time(a)} --> {_srt_time(b)}", tx, ""]
            idx += 1
    with open(out_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_srt


def windows_around(spans, margin, duration=None):
    """Fenêtres à transcrire autour de passages repérés, fusionnées.

    La marge couvre ce que la découpe va chercher au-delà des bornes brutes
    (l'annonce du présentateur avant, le retour plateau après) : sans elle, le
    texte manquerait exactement là où les bornes se décident."""
    if not spans:
        return []
    larges = [(max(0.0, s - margin),
               min(e + margin, duration) if duration else e + margin)
              for s, e in spans]
    from .segments import merge_segments
    return merge_segments(larges, 0.0)


def transcribe_windows(wav_path, windows, model=None, model_size="small",
                       lang="fr", task="transcribe", on_progress=None,
                       workdir=None):
    """Comme transcribe_all, mais sur des fenêtres seulement.

    Les temps rendus sont ceux de la source, pas ceux de la fenêtre : le reste
    de la chaîne n'a pas à savoir qu'on a découpé."""
    import os
    import tempfile

    from . import audio

    m = model or load_model(model_size)
    total = sum(e - s for s, e in windows) or 1.0
    faits = 0.0
    out = []
    tmp = tempfile.mkdtemp(prefix="dc_tx_", dir=workdir)
    try:
        for i, (deb, fin) in enumerate(windows):
            morceau = audio.extract_wav_span(
                wav_path, deb, fin, os.path.join(tmp, f"w{i:03d}.wav"))
            segs = transcribe_all(morceau, model=m, lang=lang, task=task)
            out.extend((deb + s, deb + e, t) for s, e, t in segs)
            faits += fin - deb
            if on_progress:
                on_progress(min(faits, total), total)
            os.remove(morceau)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return sorted(out)
