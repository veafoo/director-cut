from rich.console import Console
from rich.panel import Panel
from rich.progress import (BarColumn, Progress, SpinnerColumn, TextColumn,
                           TimeElapsedColumn)
from rich.table import Table
from rich.text import Text

# Caméra de reportage entre deux bobines de film.
_CAMERA = r"""
     ___                                         ___
   ,'   `.        _______________________      ,'   `.
  / () () \      |  ___              (o) o |   / () () \
 | ()   () |=====| |   |   CAM         REC |==| ()   () |
  \ () () /      | |___|      __________   |   \ () () /
   `.___,'       |__________ |          |  |    `.___,'
                            `+----------+--+
""".strip("\n").splitlines()


def splash(console):
    console.print()
    w = max((len(l) for l in _CAMERA), default=0)
    for line in _CAMERA:
        console.print(Text(line.ljust(w), style="bold cyan"),
                      justify="center", no_wrap=True, overflow="crop")
    console.print(Text("director-cut", style="bold white"), justify="center")
    console.rule(style="cyan")
    console.print(Text("Created by Veafoo", style="dim italic"),
                  justify="right")
    console.print()


def step(console, n, total, label):
    console.print(f"[bold cyan]{n}/{total}[/] {label}")


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
    console.print(Panel(tbl, title="[bold]Détection[/]", border_style="cyan",
                        expand=False))


def info(console, msg):
    console.print(f"   [dim]{msg}[/]")
