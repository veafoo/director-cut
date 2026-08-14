import base64
import glob
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".ts", ".flv")

# Sites dont l'extracteur yt-dlp natif est cassé et qui hébergent leurs vidéos
# sur Brightcove : on lit la page nous-mêmes AVANT d'essayer yt-dlp.
BRIGHTCOVE_FIRST = ("bfmtv.com",)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _ytdlp_cmd():
    return [sys.executable, "-m", "yt_dlp"]


def _fetch_html(url):
    """Récupère le HTML de façon robuste : curl d'abord (beaucoup de sites de
    presse le laissent passer là où urllib est bloqué), urllib en repli."""
    try:
        out = subprocess.run(["curl", "-sL", "-A", _UA, url],
                             check=True, capture_output=True, timeout=40)
        html = out.stdout.decode("utf-8", "replace")
        if html.strip():
            return html
    except Exception:
        pass
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "fr-FR,fr;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _brightcove_sources(url):
    """Beaucoup de chaînes (BFMTV et d'autres) hébergent leurs vidéos sur
    Brightcove, dont l'extracteur yt-dlp est régulièrement cassé. On lit la page
    et on en tire l'URL du player Brightcove + l'URL HLS signée."""
    html = _fetch_html(url)

    vid = re.search(r'data-video-id=["\'](\d+)["\']', html)
    acc = re.search(r'data-account=["\'](\d+)["\']', html)
    account = acc.group(1) if acc else None

    if not account:
        m = re.search(r'bcov_auth=([A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)', html)
        if m:
            payload = m.group(1).split(".")[1]
            payload += "=" * (-len(payload) % 4)
            try:
                account = json.loads(base64.urlsafe_b64decode(payload)).get("accid")
            except Exception:
                pass

    sources = []
    if vid and account:
        print(f"   → Brightcove détecté : compte {account}, "
              f"vidéo {vid.group(1)}")
        sources.append(
            f"https://players.brightcove.net/{account}/default_default/"
            f"index.html?videoId={vid.group(1)}")

    m3u8 = re.search(r'https://[^"\'\\ ]+\.m3u8\?bcov_auth=[^"\'\\ ]+', html)
    if m3u8:
        print("   → flux HLS signé trouvé (repli)")
        sources.append(m3u8.group(0))

    if not sources:
        print(f"   ⚠ page lue ({len(html)} caractères) mais aucun identifiant "
              "vidéo trouvé dedans")
    return sources


def get_video(source, out_dir):
    if os.path.exists(source) and source.lower().endswith(VIDEO_EXTS):
        return os.path.abspath(source)
    return download(source, out_dir)


def _run_ytdlp(src, out_tmpl, referer=None):
    cmd = _ytdlp_cmd() + ["-f", "bv*+ba/b", "--merge-output-format", "mp4"]
    if referer:
        cmd += ["--referer", referer]
    cmd += ["-o", out_tmpl, src]
    subprocess.run(cmd, check=True)


def _site_root(url):
    """Racine du site, utilisée comme Referer pour les flux Brightcove/HLS."""
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme}://{p.netloc}/" if p.scheme and p.netloc else None


def _is_page(url):
    return url.startswith("http") and not url.endswith(".m3u8")


def _brightcove_pair(url):
    """(source, referer) tirés de la page, ou [] si rien d'exploitable."""
    root = _site_root(url)
    try:
        return [(s, root) for s in _brightcove_sources(url)]
    except Exception as e:
        print(f"   ⚠ lecture de la page impossible : {e}")
        return []


def _resolve_sources(url):
    """Sources (src, referer) à tenter avec yt-dlp, dans l'ordre.

    Sites connus pour héberger sur Brightcove avec un extracteur yt-dlp cassé :
    on lit la page d'abord. Partout ailleurs : yt-dlp d'abord, la page ne sert
    que de repli (voir download)."""
    if not _is_page(url):
        return [(url, None)]
    if any(host in url for host in BRIGHTCOVE_FIRST):
        return _brightcove_pair(url) + [(url, None)]
    return [(url, None)]


def _try_sources(sources, out_tmpl):
    """Tente chaque source jusqu'à ce qu'une réussisse. True si téléchargé."""
    for src, ref in sources:
        try:
            _run_ytdlp(src, out_tmpl, referer=ref)
            return True
        except subprocess.CalledProcessError:
            continue
    return False


def download(url, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    out_tmpl = os.path.join(out_dir, "video.%(ext)s")

    sources = _resolve_sources(url)
    ok = _try_sources(sources, out_tmpl)
    if not ok and len(sources) == 1 and _is_page(url):
        # yt-dlp a échoué sur une page inconnue : c'est peut-être du Brightcove
        ok = _try_sources(_brightcove_pair(url), out_tmpl)

    if not ok:
        raise RuntimeError(
            "Le téléchargement a échoué.\n"
            "  - Vérifie yt-dlp du venv :  python -m yt_dlp --version\n"
            "  - Ou télécharge la vidéo à la main et donne son chemin :\n"
            "      director-cut run \"/chemin/vers/video.mp4\" --mode reportage"
        )

    files = [f for f in glob.glob(os.path.join(out_dir, "*"))
             if f.lower().endswith(VIDEO_EXTS)]
    if not files:
        raise RuntimeError("yt-dlp n'a produit aucune vidéo exploitable.")
    return max(files, key=os.path.getmtime)
