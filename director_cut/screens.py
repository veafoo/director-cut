import os
import subprocess


def _grab(video, t, out_png):
    subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", video,
                    "-frames:v", "1", "-q:v", "2", out_png],
                   check=True, capture_output=True)


def to_vertical(in_img, out_img, w=1080, h=1920, blur=20):
    """Passe une image 16:9 en 9:16 : la vidéo est centrée, à sa taille max en
    largeur (logo en haut à gauche + bandeau titres restent lisibles), le reste
    est comblé par un fond flou de la même image."""
    vf = (f"[0]scale={w}:{h}:force_original_aspect_ratio=increase,"
          f"boxblur={blur}:2,crop={w}:{h}[bg];"
          f"[0]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    subprocess.run(["ffmpeg", "-y", "-i", in_img, "-filter_complex", vf,
                    "-q:v", "2", out_img], check=True, capture_output=True)


def shots(video, start, end, out_dir, prefix, n=4):
    """Prend n captures réparties dans [start, end] et les passe en 9:16."""
    os.makedirs(out_dir, exist_ok=True)
    dur = max(0.1, end - start)
    out = []
    for i in range(n):
        t = start + dur * (i + 1) / (n + 1)
        raw = os.path.join(out_dir, f"{prefix}_{i + 1:02d}_raw.png")
        fin = os.path.join(out_dir, f"{prefix}_{i + 1:02d}.jpg")
        try:
            _grab(video, t, raw)
            to_vertical(raw, fin)
            out.append(fin)
        finally:
            if os.path.exists(raw):
                os.remove(raw)
    return out
