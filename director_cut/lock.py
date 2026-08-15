"""Un seul run à la fois par dossier de sortie.

Deux runs lancés en parallèle sur le même `--out` se marchent dessus : ils
partagent `raw/video.mp4` et `audio.wav`. Pendant que le premier découpe, le
second retélécharge par-dessus, et le premier voit sa source disparaître en
plein travail. L'erreur qui en sort ne ressemble en rien à la cause.

Le verrou est un fichier contenant le PID. Si le processus qui l'a posé n'existe
plus (machine redémarrée, run tué), le verrou est considéré comme périmé et
repris — sinon un plantage laisserait le dossier bloqué pour toujours.
"""
import os

LOCK_NAME = ".run.lock"


class Busy(RuntimeError):
    pass


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True         # existe, mais appartient à quelqu'un d'autre
    return True


def _holder(path):
    """PID du run en cours, ou None si le verrou est libre ou périmé."""
    try:
        with open(path, encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid() or not _alive(pid):
        return None
    return pid


class Lock:
    """Verrou de dossier, à utiliser en `with`."""

    def __init__(self, out_dir):
        self.path = os.path.join(out_dir, LOCK_NAME)
        self.taken = False

    def __enter__(self):
        pid = _holder(self.path)
        if pid is not None:
            raise Busy(
                f"Un autre run travaille déjà dans ce dossier (processus {pid}). "
                "Attends qu'il finisse, ou lance celui-ci avec un --out "
                "différent.")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        self.taken = True
        return self

    def __exit__(self, *exc):
        if self.taken and _holder_is_us(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass
        return False


def _holder_is_us(path):
    try:
        with open(path, encoding="utf-8") as f:
            return int(f.read().strip()) == os.getpid()
    except (OSError, ValueError):
        return False
