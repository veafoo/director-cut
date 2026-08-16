"""Vignettes 9:16 pour les réseaux sociaux.

Rendu calé sur les vignettes publiées par les chaînes : image plein cadre
(recadrage 9:16, pas de bandes ni de fond flou) et logo posé à l'emplacement du
gabarit de la chaîne (voir brands.py).

Deux choses jouent sur la netteté, dans cet ordre d'importance :
1. le choix de l'instant — une frame prise en plein mouvement est floue quoi
   qu'on fasse ; on en teste plusieurs autour de l'instant visé et on garde la
   plus nette ;
2. la chaîne de rendu — recadrage sur la source, rééchantillonnage Lanczos,
   puis masque flou (unsharp) pour compenser l'agrandissement.
"""
import os
import warnings

import numpy as np

from . import ff
from .brands import OUT_H, OUT_W

# Force du masque flou. Au-delà de ~1.2 les contours deviennent cartonneux.
SHARPEN = 0.8
# Après retouche IA l'image est déjà nette : un masque flou fort la cartonne.
SHARPEN_ENHANCED = 0.2
# Fenêtre (s) et nombre de frames candidates pour le choix de l'instant.
PICK_WINDOW = 0.6
PICK_CANDIDATES = 5
# Sous cette durée, un plan est une transition ou un filé : mauvaise vignette.
MIN_SHOT = 1.5


def _run(cmd):
    ff.run(cmd)


# --- choix de l'instant le plus net --------------------------------------

def read_frame(video, t):
    """Frame de la vidéo à l'instant t, en numpy RGB à la définition native."""
    size = ff.capture(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video]
    ).decode().strip().split("x")
    w, h = int(size[0]), int(size[1])
    raw = ff.capture(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", video,
         "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    if len(raw) < w * h * 3:
        raise RuntimeError(f"frame illisible à {t:.2f}s dans {video}")
    return np.frombuffer(raw[:w * h * 3], np.uint8).reshape(h, w, 3)


def _gray_frame(video, t, size=192):
    """Rend une mini-image en niveaux de gris (numpy 2D) pour la mesure."""
    out = ff.capture(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", video,
         "-frames:v", "1", "-vf", f"scale={size}:{size}",
         "-pix_fmt", "gray", "-f", "rawvideo", "-"])
    if len(out) < size * size:
        return None
    return np.frombuffer(out[:size * size], np.uint8).reshape(size, size)


def sharpness(img):
    """Variance du laplacien : mesure de netteté classique. Une frame prise en
    plein panoramique ou sur un mouvement rapide s'effondre sur cet indicateur."""
    a = np.asarray(img, dtype=np.float32)
    lap = (-4.0 * a[1:-1, 1:-1] + a[:-2, 1:-1] + a[2:, 1:-1]
           + a[1:-1, :-2] + a[1:-1, 2:])
    return float(lap.var())


def best_time(video, t, window=PICK_WINDOW, candidates=PICK_CANDIDATES):
    """Instant le moins flou dans [t - window/2, t + window/2]."""
    if candidates < 2 or window <= 0:
        return t
    step = window / (candidates - 1)
    best, best_score = t, -1.0
    for i in range(candidates):
        c = max(0.0, t - window / 2 + i * step)
        try:
            img = _gray_frame(video, c)
        except ff.FFmpegError:
            continue
        if img is None:
            continue
        score = sharpness(img)
        if score > best_score:
            best, best_score = c, score
    return best


# --- rendu ----------------------------------------------------------------

def vertical_chain(w=OUT_W, h=OUT_H, sharpen=SHARPEN, strip_top=0.0,
                   strip_bottom=0.0):
    """Filtre ffmpeg : recadrage plein cadre en 9:16, puis remise à l'échelle.

    Le recadrage prend la plus grande zone 9:16 possible et la centre : l'image
    remplit toute la vignette, comme sur les gabarits.

    strip_top / strip_bottom retirent d'abord les bandes d'habillage antenne de
    la source. Ça sort le bandeau du direct du cadre, au prix d'un
    agrandissement plus fort (donc d'une image moins fine)."""
    chain = ""
    if strip_top or strip_bottom:
        keep = 1.0 - strip_top - strip_bottom
        chain += f"crop=iw:ih*{keep:.4f}:0:ih*{strip_top:.4f},"
    chain += (f"crop='min(iw,ih*{w}/{h})':'min(ih,iw*{h}/{w})',"
              f"scale={w}:{h}:flags=lanczos")
    if sharpen:
        chain += f",unsharp=5:5:{sharpen}:5:5:0.0"
    return chain


def _render_cmd(inputs, out_img, brand, w, h, sharpen, seek=None, strip=True):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if seek is not None:
        cmd += ["-ss", f"{seek:.3f}"]
    cmd += ["-i", inputs]
    chain = vertical_chain(
        w, h, sharpen,
        strip_top=getattr(brand, "strip_top", 0.0) if strip else 0.0,
        strip_bottom=getattr(brand, "strip_bottom", 0.0) if strip else 0.0)
    if brand is None:
        cmd += ["-vf", chain]
    else:
        x, y, logo_h = brand.box(w, h)
        cmd += ["-i", brand.logo, "-filter_complex",
                f"[0:v]{chain}[bg];"
                f"[1:v]scale=-1:{logo_h}:flags=lanczos[logo];"
                f"[bg][logo]overlay={x}:{y}"]
    cmd += ["-frames:v", "1", "-q:v", "2", out_img]
    return cmd


def to_vertical(in_img, out_img, brand=None, w=OUT_W, h=OUT_H, sharpen=SHARPEN):
    """Passe une image en vignette 9:16 (recadrage plein cadre + logo)."""
    _run(_render_cmd(in_img, out_img, brand, w, h, sharpen))
    return out_img


def grab_vertical(video, t, out_img, brand=None, w=OUT_W, h=OUT_H,
                  sharpen=SHARPEN, enhance_opts=None):
    """Capture l'instant t d'une vidéo en vignette 9:16.

    Sans retouche IA : un seul passage ffmpeg, on recadre sur la source pleine
    définition. Avec : la frame passe d'abord par l'effacement de l'habillage
    et la super-résolution, et ffmpeg ne fait plus que la mise à la taille
    finale et la pose du logo."""
    if enhance_opts:
        try:
            return _grab_enhanced(video, t, out_img, brand, w, h, enhance_opts)
        except Exception as e:                      # noqa: BLE001
            # La retouche est un bonus ; la découpe, non. Une vignette non
            # retouchée vaut mieux qu'un run perdu au dernier sixième.
            warnings.warn(f"retouche impossible sur cette vignette ({e}) : "
                          "rendu sans retouche", RuntimeWarning)
    _run(_render_cmd(video, out_img, brand, w, h, sharpen, seek=t))
    return out_img


def _grab_enhanced(video, t, out_img, brand, w, h, enhance_opts):
    from PIL import Image

    from . import enhance
    frame = enhance.prepare(read_frame(video, t),
                            boxes=getattr(brand, "furniture", ()),
                            strip_top=getattr(brand, "strip_top", 0.0),
                            strip_bottom=getattr(brand, "strip_bottom", 0.0),
                            out_w=w, out_h=h, **enhance_opts)
    tmp = out_img + ".enhanced.png"
    try:
        Image.fromarray(frame).save(tmp)
        # L'image est déjà recadrée, détourée et nette : ffmpeg ne fait plus
        # que la mise à la taille finale et la pose du logo.
        _run(_render_cmd(tmp, out_img, brand, w, h, SHARPEN_ENHANCED,
                         strip=False))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return out_img


def pick_shots(cuts, start, end, n, min_shot=MIN_SHOT):
    """Un plan différent par vignette, répartis sur tout le passage.

    Répartir des instants à intervalles fixes, sans regarder où sont les plans,
    fait tomber sur des transitions et donne quatre fois le même cadre quand un
    plan dure longtemps. On découpe donc le passage en plans, on écarte les
    plus courts (transitions, panoramiques filés), et on en prend n bien
    espacés. Un plan long est réutilisé, mais en visant un endroit différent,
    plutôt que de rendre moins de vignettes que demandé."""
    edges = [start] + [c for c in sorted(cuts or []) if start < c < end] + [end]
    shots = [(a, b) for a, b in zip(edges, edges[1:]) if b - a >= min_shot]
    if not shots:
        shots = [(start, max(end, start + 0.1))]

    if len(shots) >= n:
        step = (len(shots) - 1) / max(1, n - 1) if n > 1 else 0
        chosen = [shots[round(i * step)] for i in range(n)]
        return [((a + b) / 2, a, b) for a, b in chosen]

    # Moins de plans que de vignettes : on répartit dans les plus longs.
    out = []
    for i in range(n):
        a, b = shots[i % len(shots)]
        k, total = i // len(shots), (n + len(shots) - 1) // len(shots)
        out.append((a + (b - a) * (k + 1) / (total + 1), a, b))
    return sorted(out)


def shots(video, start, end, out_dir, prefix, n=4, brand=None,
          window=PICK_WINDOW, candidates=PICK_CANDIDATES, sharpen=SHARPEN,
          enhance_opts=None, cuts=None):
    """N vignettes 9:16 : un plan distinct chacune, sur sa frame la plus nette."""
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for i, (t, lo, hi) in enumerate(pick_shots(cuts, start, max(end, start + 0.1),
                                               n), 1):
        # La recherche de netteté ne doit pas déborder sur le plan voisin.
        span = min(window, max(0.0, (hi - lo) - 0.2))
        t = best_time(video, t, window=span, candidates=candidates)
        fin = os.path.join(out_dir, f"{prefix}_{i:02d}.jpg")
        grab_vertical(video, t, fin, brand=brand, sharpen=sharpen,
                      enhance_opts=enhance_opts)
        out.append(fin)
    return out
