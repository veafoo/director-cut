def load_model(model_size="small"):
    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device="auto", compute_type="auto")


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
