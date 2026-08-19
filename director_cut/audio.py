from . import ff


def extract_wav(video_path, out_path, sr=16000):
    """Extrait l'audio en wav mono 16 kHz (format attendu par les modèles)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ac", "1",
        "-ar", str(sr),
        "-vn",
        out_path,
    ]
    ff.run(cmd)
    return out_path


def extract_clip_audio(video_path, start, end, out_path):
    """Extrait l'audio d'un passage en m4a (aac)."""
    ff.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", video_path,
            "-t", f"{end - start:.3f}", "-vn", "-c:a", "aac", out_path])
    return out_path


def extract_wav_span(wav_path, start, end, out_path, sr=16000):
    """Découpe une fenêtre du wav, au même format.

    Transcrire une source de deux heures pour n'en garder que trois minutes,
    c'est payer quarante fois le prix du résultat. On ne donne au modèle que
    les fenêtres qui nous intéressent."""
    ff.run(["ffmpeg", "-y", "-ss", f"{max(0.0, start):.3f}",
            "-to", f"{end:.3f}", "-i", wav_path,
            "-ac", "1", "-ar", str(sr), "-vn", out_path])
    return out_path
