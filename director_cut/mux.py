from . import ff


def mux_mkv(video_mp4, subs, out_mkv):
    """Crée un .mkv qui embarque les pistes de sous-titres.
    subs = [(chemin_srt, code_langue), ...] ex [(fr,'fre'), (en,'eng')]."""
    cmd = ["ffmpeg", "-y", "-i", video_mp4]
    for path, _ in subs:
        cmd += ["-i", path]
    cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
    for i, _ in enumerate(subs):
        cmd += ["-map", str(i + 1)]
    cmd += ["-c:v", "copy", "-c:a", "copy", "-c:s", "srt"]
    for i, (_, lang) in enumerate(subs):
        cmd += [f"-metadata:s:s:{i}", f"language={lang}"]
    cmd += [out_mkv]
    ff.run(cmd)
    return out_mkv
