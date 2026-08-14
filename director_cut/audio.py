import subprocess


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
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def extract_clip_audio(video_path, start, end, out_path):
    """Extrait l'audio d'un passage en m4a (aac)."""
    subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", video_path,
                    "-t", f"{end - start:.3f}", "-vn", "-c:a", "aac", out_path],
                   check=True, capture_output=True)
    return out_path
