"""Appels ffmpeg/ffprobe.

Une seule raison d'exister : quand ffmpeg échoue, il faut savoir POURQUOI.
`subprocess.run(check=True, capture_output=True)` lève une CalledProcessError
qui affiche la commande et un code de retour, et jette le message d'erreur.
L'utilisatrice se retrouve avec « returned non-zero exit status 254 » et rien
d'autre — alors que ffmpeg avait écrit la réponse sur stderr.
"""
import subprocess


class FFmpegError(RuntimeError):
    def __init__(self, cmd, code, stderr):
        self.cmd = cmd
        self.code = code
        self.stderr = stderr
        super().__init__(f"{_reason(stderr)} (ffmpeg a rendu {code})")


def _reason(stderr):
    """La ou les lignes qui expliquent l'échec, pas la bannière de version.

    Le motif est comparé sur la ligne dégagée de son indentation : ffmpeg
    indente la moitié de sa bannière, et pas toujours pareil selon la version."""
    skip = ("ffmpeg version", "ffprobe version", "built with", "configuration:",
            "lib", "Input #", "Output #", "Stream ", "Duration:", "Metadata:",
            "encoder", "Press [q]")
    useful = []
    for line in (stderr or "").splitlines():
        bare = line.strip()
        if bare and not bare.startswith(skip):
            useful.append(bare)
    if not useful:
        return "échec de ffmpeg, sans message"
    return " / ".join(useful[-2:])


def run(cmd):
    """Lance ffmpeg. Lève une FFmpegError qui porte la raison de l'échec."""
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise FFmpegError(cmd, p.returncode,
                          p.stderr.decode("utf-8", "replace"))
    return p


def capture(cmd):
    """Lance ffmpeg et renvoie sa sortie standard (flux brut, JSON, …)."""
    return run(cmd).stdout
