"""Retouche IA des vignettes : effacer l'habillage antenne, puis agrandir.

C'est l'industrialisation de ce qui se faisait à la main image par image :
1. **Effacer** le bandeau, l'horloge, la météo et le logo de la chaîne. Modèle
   LaMa (inpainting), qui reconstruit le décor derrière le graphisme au lieu de
   le recouvrir. Sans ça, un recadrage 9:16 coupe le bandeau en plein milieu.
2. **Agrandir** proprement. La source est du 720p, la vignette du 1080x1920 :
   il y a un facteur 2.7 à combler. Real-ESRGAN reconstruit ×4, on redescend
   ensuite à la taille cible — une réduction depuis une image sur-résolue est
   bien plus fine qu'un agrandissement direct.

Les deux modèles sont des poids publics téléchargés une fois (`director-cut
models`) et gardés dans ~/.cache/director-cut. Aucun appel réseau ensuite,
aucune donnée qui sort de la machine, et un rendu reproductible.

Aucune dépendance en plus : les deux tournent sur le torch déjà installé pour
la diarisation.
"""
import os
import subprocess
import threading

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

CACHE = os.path.expanduser("~/.cache/director-cut")

MODELS = {
    # Inpainting. TorchScript : se charge sans code d'architecture.
    "lama": ("big-lama.pt", "https://github.com/enesmsahin/"
             "simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"),
    # Super-résolution ×4. Poids RRDBNet officiels (architecture ci-dessous).
    "esrgan": ("realesrgan_x4plus.pth", "https://github.com/xinntao/"
               "Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"),
}

_cache = {}
# Les passages sont traités en parallèle, mais le GPU ne l'est pas : sur Mac
# (MPS) des inférences concurrentes plantent. On sérialise, ce qui ne coûte
# rien puisque le GPU est de toute façon le goulet.
_gpu = threading.Lock()


def model_path(name):
    return os.path.join(CACHE, MODELS[name][0])


def is_ready(name):
    return os.path.exists(model_path(name))


def download(name, quiet=False):
    """Télécharge un modèle s'il manque. Via curl : le Python de macOS n'a pas
    toujours les certificats racine, curl si."""
    dest = model_path(name)
    if os.path.exists(dest):
        return dest
    os.makedirs(CACHE, exist_ok=True)
    tmp = dest + ".part"
    cmd = ["curl", "-L", "--fail", "-o", tmp, MODELS[name][1]]
    if quiet:
        cmd.insert(1, "-s")
    subprocess.run(cmd, check=True)
    os.replace(tmp, dest)
    return dest


def device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


# --- effacement de l'habillage (LaMa) ------------------------------------

def _lama():
    if "lama" not in _cache:
        m = torch.jit.load(download("lama"), map_location=device())
        m.eval()
        _cache["lama"] = m
    return _cache["lama"]


def _pad_to(x, mod=8):
    h, w = x.shape[-2:]
    ph, pw = (-h) % mod, (-w) % mod
    if ph or pw:
        x = F.pad(x, (0, pw, 0, ph), mode="reflect")
    return x, h, w


def erase(rgb, mask):
    """Reconstruit le décor sous `mask`. rgb = HxWx3 uint8, mask = HxW bool."""
    dev = device()
    img = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1)[None]
    img = img.float().div_(255).to(dev)
    msk = torch.from_numpy(np.ascontiguousarray(mask))[None, None].float().to(dev)
    img, h, w = _pad_to(img)
    msk, _, _ = _pad_to(msk)
    with _gpu, torch.inference_mode():
        out = _lama()(img, (msk > 0).float())
    out = out[0, :, :h, :w].permute(1, 2, 0).clamp(0, 1).mul(255)
    return out.to(torch.uint8).cpu().numpy()


# --- super-résolution (Real-ESRGAN / RRDBNet) ----------------------------

class _ResidualDenseBlock(nn.Module):
    def __init__(self, nf=64, gc=32):
        super().__init__()
        for i in range(1, 6):
            out = gc if i < 5 else nf
            setattr(self, f"conv{i}", nn.Conv2d(nf + (i - 1) * gc, out, 3, 1, 1))
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        feats = [x]
        for i in range(1, 5):
            feats.append(self.lrelu(getattr(self, f"conv{i}")(torch.cat(feats, 1))))
        x5 = self.conv5(torch.cat(feats, 1))
        return x5 * 0.2 + x


class _RRDB(nn.Module):
    def __init__(self, nf=64, gc=32):
        super().__init__()
        self.rdb1 = _ResidualDenseBlock(nf, gc)
        self.rdb2 = _ResidualDenseBlock(nf, gc)
        self.rdb3 = _ResidualDenseBlock(nf, gc)

    def forward(self, x):
        return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x


class RRDBNet(nn.Module):
    """Générateur Real-ESRGAN ×4. Reconstruit ici pour charger les poids
    officiels sans tirer basicsr (qui casse avec torch/numpy récents)."""

    def __init__(self, nf=64, nb=23, gc=32):
        super().__init__()
        self.conv_first = nn.Conv2d(3, nf, 3, 1, 1)
        self.body = nn.Sequential(*[_RRDB(nf, gc) for _ in range(nb)])
        self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        for up in (self.conv_up1, self.conv_up2):
            feat = self.lrelu(up(F.interpolate(feat, scale_factor=2,
                                               mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


def _esrgan():
    if "esrgan" not in _cache:
        net = RRDBNet()
        sd = torch.load(download("esrgan"), map_location="cpu", weights_only=True)
        net.load_state_dict(sd.get("params_ema", sd), strict=True)
        net.eval().to(device())
        _cache["esrgan"] = net
    return _cache["esrgan"]


def upscale(rgb, tile=256, overlap=16):
    """Agrandit ×4. Traité par tuiles : une image entière en une passe fait
    exploser la mémoire, et le recouvrement évite les coutures visibles."""
    dev = device()
    net = _esrgan()
    x = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1)[None]
    x = x.float().div_(255).to(dev)
    _, _, h, w = x.shape
    out = torch.zeros((1, 3, h * 4, w * 4), dtype=torch.float32, device=dev)

    step = max(1, tile - overlap)
    for y0 in range(0, h, step):
        for x0 in range(0, w, step):
            y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
            with _gpu, torch.inference_mode():
                piece = net(x[:, :, y0:y1, x0:x1])
            # On jette le recouvrement sauf sur les bords de l'image, où il
            # n'y a pas de tuile voisine pour le remplacer.
            ty = 0 if y0 == 0 else overlap // 2
            tx = 0 if x0 == 0 else overlap // 2
            out[:, :, (y0 + ty) * 4:y1 * 4, (x0 + tx) * 4:x1 * 4] = \
                piece[:, :, ty * 4:, tx * 4:]
            if x1 >= w:
                break
        if y1 >= h:
            break
    out = out[0].permute(1, 2, 0).clamp(0, 1).mul(255)
    return out.to(torch.uint8).cpu().numpy()


# --- masque d'habillage ---------------------------------------------------

def _rect(shape, box, grow):
    h, w = shape[:2]
    left, top, right, bottom = box
    return (max(0, int(left * w) - grow), max(0, int(top * h) - grow),
            min(w, int(right * w) + grow), min(h, int(bottom * h) + grow))


def is_present(frame, item, grow=0):
    """Un élément intermittent est-il à l'antenne sur cette frame ?

    Test par couleur : le synthé occupe la moitié de sa boîte avec l'aplat de
    la charte, là où un décor naturel n'en a quasiment rien. Sans couleur de
    référence, l'élément est considéré comme toujours présent."""
    if item.color is None:
        return True
    if frame is None:
        return False        # dans le doute, on n'efface pas de vraie image
    x0, y0, x1, y1 = _rect(frame.shape, item.box, grow)
    sub = frame[y0:y1, x0:x1].astype(np.int16)
    if sub.size == 0:
        return False
    close = np.abs(sub - np.asarray(item.color, np.int16)).sum(2) < 45
    return float(close.mean()) >= item.cover


def furniture_mask(shape, items, frame=None, grow=6):
    """Masque des zones d'habillage à effacer.

    Les boîtes sont un peu élargies : un liseré de graphisme oublié suffit à
    faire recopier sa couleur par le modèle sur toute la zone."""
    mask = np.zeros(shape[:2], dtype=bool)
    for item in items:
        if not is_present(frame, item):
            continue
        x0, y0, x1, y1 = _rect(shape, item.box, grow)
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True
    return mask


def crop_9_16(rgb, out_w=1080, out_h=1920):
    """Découpe la plus grande zone au format cible, centrée."""
    h, w = rgb.shape[:2]
    cw = min(w, round(h * out_w / out_h))
    ch = min(h, round(w * out_h / out_w))
    x0 = (w - cw) // 2
    y0 = (h - ch) // 2
    return rgb[y0:y0 + ch, x0:x0 + cw]


# --- enchaînement ---------------------------------------------------------

def prepare(rgb, boxes=(), clean=True, sharpen=True, strip_top=0.0,
            strip_bottom=0.0, out_w=1080, out_h=1920):
    """Frame de diffusion -> image prête à devenir une vignette.

    L'ordre compte : on efface AVANT de recadrer (le modèle a besoin de toute
    l'image autour du bandeau pour reconstruire le décor), et on agrandit APRÈS
    (inutile de sur-résoudre les deux tiers de l'image qui partent au recadrage).

    strip_top / strip_bottom sortent en plus les bandes qui touchent un bord.
    Ce sont celles que le modèle reconstruit le moins bien : il n'a de contexte
    que d'un seul côté. Le zoom que ça coûte est rattrapé par la super-résolution.
    """
    if clean and len(boxes):
        mask = furniture_mask(rgb.shape, boxes, frame=rgb)
        if mask.any():
            rgb = erase(rgb, mask)
    if strip_top or strip_bottom:
        h = rgb.shape[0]
        rgb = rgb[int(strip_top * h):h - int(strip_bottom * h)]
    rgb = crop_9_16(rgb, out_w, out_h)
    if sharpen and rgb.shape[1] < out_w:
        rgb = upscale(rgb)
    return rgb


def missing(clean=True, sharpen=True):
    """Modèles nécessaires qui ne sont pas encore sur la machine."""
    need = (["lama"] if clean else []) + (["esrgan"] if sharpen else [])
    return [n for n in need if not is_ready(n)]
