"""Une signature sonore au lancement.

Trois règles, dans cet ordre :

1. **Jamais bloquant.** Le son part en arrière-plan et on ne l'attend pas. Un
   lecteur absent, un fichier corrompu, une machine sans carte son : le run
   continue comme si de rien n'était.
2. **Rien de musical dans le dépôt.** Il est public : on ne peut pas y déposer
   une musique dont on n'a pas les droits. La signature est donc *fabriquée*
   avec ffmpeg — déjà nécessaire au reste — puis mise en cache.
3. **Remplaçable.** Un fichier `jingle.*` déposé à la racine du projet l'emporte
   sur la signature d'origine, et reste hors du dépôt comme les autres fichiers
   personnels.
"""
import os
import subprocess

CACHE = os.path.expanduser("~/.cache/director-cut")
SIGNATURE = os.path.join(CACHE, "signature.wav")
EXTENSIONS = (".wav", ".mp3", ".m4a", ".aiff", ".aif", ".aac", ".flac", ".ogg")

# Trois notes montantes, une demi-seconde. Court, parce qu'on l'entendra à
# chaque lancement.
NOTES = ((587, 0.10), (880, 0.10), (1175, 0.30))


def fichier_perso(workdir="."):
    """Le fichier déposé par la personne, s'il y en a un."""
    try:
        for f in sorted(os.listdir(workdir)):
            if f.lower().startswith("jingle") and f.lower().endswith(EXTENSIONS):
                return os.path.join(workdir, f)
    except OSError:
        pass
    return None


def lecteur():
    """De quoi jouer un son, selon la machine. None si rien n'est disponible."""
    for cmd in (["afplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
        chemin = _trouver(cmd[0])
        if chemin:
            return [chemin] + cmd[1:]
    return None


def _trouver(nom):
    from shutil import which
    return which(nom)


def fabriquer(chemin=SIGNATURE):
    """Synthétise la signature une fois pour toutes."""
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    entrees, etiquettes = [], ""
    for i, (freq, duree) in enumerate(NOTES):
        entrees += ["-f", "lavfi", "-i",
                    f"sine=frequency={freq}:duration={duree},volume=0.4"]
        etiquettes += f"[{i}]"
    fin = sum(d for _, d in NOTES)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *entrees, "-filter_complex",
         f"{etiquettes}concat=n={len(NOTES)}:v=0:a=1,"
         f"afade=t=out:st={fin - 0.15:.2f}:d=0.15", chemin],
        check=True, capture_output=True)
    return chemin


def jouer(workdir=".", actif=True, interactif=True, lancer=None):
    """Joue la signature. Rend True si un son est parti, False sinon.

    `lancer` est injecté par les tests : rien ne doit sortir des haut-parleurs
    pendant une suite de tests."""
    if not actif or not interactif:
        return False
    joueur = lecteur()
    if not joueur:
        return False
    try:
        son = fichier_perso(workdir)
        if son is None:
            son = SIGNATURE if os.path.exists(SIGNATURE) else fabriquer()
        demarrer = lancer or _en_arriere_plan
        demarrer(joueur + [son])
        return True
    except Exception:                          # noqa: BLE001
        # Un son raté ne doit jamais empêcher un run de démarrer.
        return False


def _en_arriere_plan(cmd):
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
