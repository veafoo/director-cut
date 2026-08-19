import getpass
import os
from importlib import metadata

from rich import box
from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.progress import (BarColumn, Progress, SpinnerColumn, TextColumn,
                           TimeElapsedColumn)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# Une seule couleur pour tout l'outil.
ACCENT = "blue"

# Caméra d'épaule : deux bobines, le témoin REC, le fût de l'objectif à droite.
_CAMERA = r"""
    ▗▄▖   ▗▄▖
    ▐█▌   ▐█▌
 ▗▄▄▟▄▄▄▄▄▟▄▄▄▖
 ▐ ▗ REC      ▌▄▄
 ▐            ▌██
 ▝▀▀▀▀▀▀▀▀▀▀▀▀▘▀▀
""".strip("\n").splitlines()

_TIPS = (
    'director-cut run "URL" --mode reportage',
    "Une option s'applique aux vidéos qui la suivent.",
)

_NEWS = (
    "Les bornes d'un passage suivent les tours de parole",
    "Plusieurs vidéos en une commande, un réglage par vidéo",
    "Une rediffusion ne ressort plus en double",
)

# En dessous, deux colonnes ne tiennent plus : on empile.
_WIDE = 92
_LEFT = 40


def _version():
    try:
        return metadata.version("director-cut")
    except metadata.PackageNotFoundError:      # dépôt non installé
        return ""


def _user_name():
    """Le prénom du compte de la machine, à défaut son identifiant."""
    name = ""
    try:
        import pwd
        name = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
    except Exception:                          # noqa: BLE001  (Windows, compte sans gecos)
        pass
    if not name:
        try:
            name = getpass.getuser()
        except Exception:                      # noqa: BLE001  (ni env ni compte)
            return ""
    first = name.split()[0] if name.split() else ""
    return first[:1].upper() + first[1:]


def _cwd():
    path = os.getcwd()
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path


def _jobs_line(jobs):
    """« 2 vidéos · reportage, jt » — ce que la commande va traiter."""
    if not jobs:
        return ""
    modes = []
    for job in jobs:
        mode = job.get("mode")
        if mode and mode not in modes:
            modes.append(mode)
    count = f"{len(jobs)} vidéos" if len(jobs) > 1 else "1 vidéo"
    return f"{count} · {', '.join(modes)}" if modes else count


def _welcome(jobs):
    name = _user_name()
    hello = f"Bienvenue, {name} !" if name else "Bienvenue !"
    lines = [
        Text(""),
        Text(hello, style="bold", justify="center"),
        Text(""),
        Align.center(Text("\n".join(_CAMERA), style=f"bold {ACCENT}"),
                     pad=False),
        Text(""),
    ]
    jobs_line = _jobs_line(jobs)
    if jobs_line:
        lines.append(Text(jobs_line, style="dim", justify="center"))
    lines.append(Text(f"{_cwd()} · Veafoo", style="dim", justify="center",
                      overflow="ellipsis", no_wrap=True))
    return Group(*lines)


def _help():
    lines = [Text("Pour commencer", style="bold")]
    lines += [Text(t, style="dim") for t in _TIPS]
    lines.append(Rule(style=ACCENT))
    lines.append(Text("Nouveautés", style="bold"))
    lines += [Text(n, style="dim") for n in _NEWS]
    lines.append(Text("Détails : README.md", style="dim"))
    return Group(*lines)


def splash(console, jobs=None):
    version = _version()
    title = f"[bold]director-cut[/]{f' v{version}' if version else ''}"

    if console.width >= _WIDE:
        # box.MINIMAL sans bord extérieur : il ne reste que le trait vertical
        # entre les deux colonnes, comme la barre du panneau.
        body = Table(box=box.MINIMAL, show_header=False, show_edge=False,
                     border_style=ACCENT, expand=True, pad_edge=False)
        body.add_column(width=_LEFT)
        body.add_column(ratio=1)
        body.add_row(_welcome(jobs), _help())
    else:
        body = Group(_welcome(jobs), Rule(style=ACCENT), _help())

    console.print()
    console.print(Panel(body, title=title, title_align="left",
                        border_style=ACCENT, box=box.ROUNDED))
    console.print()


def step(console, n, total, label):
    console.print(f"[bold {ACCENT}]{n}/{total}[/] {label}")


def make_progress(console):
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )


def detection_summary(console, mode, label, score, threshold, n_passages,
                      total_kept, name_status=None):
    tbl = Table(show_header=False, box=None, pad_edge=False)
    tbl.add_column(style="bold")
    tbl.add_column()
    labels = {"jt": "JT complet", "reportage": "Reportage", "chronique": "Chronique"}
    tbl.add_row("Mode", labels.get(mode, mode))
    tbl.add_row("Voix détectée",
                f"{label}  (similarité {score:.2f} · seuil auto {threshold:.2f})")
    if name_status:
        tbl.add_row("Lancement", name_status)
    tbl.add_row("Passages retenus", str(n_passages))
    tbl.add_row("Durée totale", f"{total_kept:.0f} s")
    console.print(Panel(tbl, title="[bold]Détection[/]", border_style=ACCENT,
                        expand=False))


def info(console, msg):
    console.print(f"   [dim]{msg}[/]")


def timings(console, chrono, titre="Temps"):
    """Le détail par étape, avec sa part du total.

    La part compte autant que la durée : c'est elle qui dit où chercher quand
    un run est trop long."""
    from .chrono import hms

    etapes = chrono.items()
    total = chrono.total
    tbl = Table(show_header=False, box=None, pad_edge=False)
    tbl.add_column(style="bold")
    tbl.add_column(justify="right")
    tbl.add_column(justify="right", style="dim")
    for nom, secondes in etapes:
        part = f"{secondes / total * 100:.0f} %" if total else ""
        tbl.add_row(nom, hms(secondes), part)
    if etapes:
        tbl.add_row("", "", "")
    tbl.add_row("Total", hms(total), "")
    console.print(Panel(tbl, title=f"[bold]{titre}[/]", border_style=ACCENT,
                        expand=False))


def timings_recap(console, lignes):
    """Récapitulatif par vidéo : [(libellé, chrono|None, secondes), …].

    Sur un lot, la question n'est plus « combien de temps » mais « laquelle a
    tout pris »."""
    from .chrono import hms

    tbl = Table(show_header=True, box=None, pad_edge=False)
    tbl.add_column("Vidéo", style="bold")
    tbl.add_column("Temps", justify="right")
    total = 0.0
    for libelle, secondes in lignes:
        tbl.add_row(libelle, hms(secondes))
        total += secondes
    tbl.add_row("", "")
    tbl.add_row("Total", hms(total))
    console.print(Panel(tbl, title="[bold]Temps par vidéo[/]",
                        border_style=ACCENT, expand=False))
