import datetime
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import click
from rich.console import Console

from . import (audio, brands, cut, diarize, download, enroll, identify, launch,
               lock, mux, scenes, screens, segments, ui)

SAMPLE_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".mp3", ".m4a", ".aac",
               ".flac", ".wav")


def _read_token(workdir, opt):
    if opt:
        return opt
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    p = os.path.join(workdir, ".hf_token")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    return None


def _read_names(workdir, opt):
    if opt:
        return list(opt)
    p = os.path.join(workdir, "names.txt")
    if os.path.exists(p):
        return [l.strip() for l in open(p, encoding="utf-8") if l.strip()]
    return []


def _guess_date(source):
    """Devine la date du journal/émission depuis l'URL ou le nom de fichier."""
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", source or "")
    if m:
        y, mo, d = m.groups()
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{mo}-{d}"
    return datetime.date.today().isoformat()


def _find_samples(workdir):
    """samples/ (extraits propres) prioritaire, sinon sample.* (segment brut)."""
    sdir = os.path.join(workdir, "samples")
    if os.path.isdir(sdir):
        files = [os.path.join(sdir, f) for f in sorted(os.listdir(sdir))
                 if f.lower().endswith(SAMPLE_EXTS)]
        if files:
            return files, "clean"
    for f in sorted(os.listdir(workdir)):
        if f.lower().startswith("sample") and f.lower().endswith(SAMPLE_EXTS):
            return [os.path.join(workdir, f)], "segment"
    return [], None


def _ensure_reference(console, ref, workdir, hf_token):
    samples, kind = _find_samples(workdir)
    if os.path.exists(ref):
        if not samples:
            return
        ref_m = os.path.getmtime(ref)
        if all(os.path.getmtime(s) <= ref_m for s in samples):
            return
        ui.info(console, "sample plus récent détecté -> recalcul de l'empreinte")

    if not samples:
        raise click.ClickException(
            "Pas d'empreinte vocale et pas de sample. Dépose un extrait de sa "
            "voix sous le nom 'sample.mp4' à la racine du projet, puis relance.")

    console.print("[bold magenta]» Empreinte vocale (automatique)…[/]")
    if kind == "segment":
        ui.info(console, f"analyse de {os.path.basename(samples[0])} "
                         "(repérage du locuteur dominant)")
        _, thr, dur, _ = enroll.enroll_from_chronique(
            samples[0], ref, hf_token, diarize.diarize, workdir)
        ui.info(console, f"empreinte créée · {dur:.0f}s de voix · "
                         f"seuil auto-calibré {thr:.2f}")
    else:
        _, thr, _ = enroll.enroll_from_clean_samples(samples, ref)
        ui.info(console, f"empreinte créée depuis {len(samples)} extrait(s) · "
                         f"seuil auto-calibré {thr:.2f}")


def _retouche_opts(console, template):
    """Ce que la retouche IA peut faire ici, vu les modèles installés.

    Rien n'est bloquant : un modèle absent désactive juste l'étape concernée,
    avec un message. La découpe, elle, doit aboutir dans tous les cas."""
    from . import enhance

    clean = bool(template and template.furniture)
    if template and not template.furniture:
        ui.info(console, f"pas d'habillage relevé pour {template.name} : "
                         "bandeau non effacé (voir README, clé 'furniture')")
    absents = enhance.missing(clean=clean, sharpen=True)
    if absents:
        ui.info(console, f"retouche IA ignorée, modèle(s) manquant(s) : "
                         f"{', '.join(absents)} — lance 'director-cut models'")
        return None
    if not clean:
        return {"clean": False, "sharpen": True}
    return {"clean": True, "sharpen": True}


@click.group()
def cli():
    """Découpe les passages d'une personne dans une vidéo, par sa voix."""


@cli.command("run")
@click.argument("url")
@click.option("--mode", type=click.Choice(["chronique", "reportage", "jt"]),
              default="chronique",
              help="chronique = plateau -> annonce du sujet suivant ; "
                   "reportage = plateau -> retour plateau (présentateur exclu) ; "
                   "jt = présentation de toute l'édition.")
@click.option("--merge-gap", default=None, type=float,
              help="Trou max pour regrouper les prises (défaut selon le mode).")
@click.option("--out", default="sortie", help="Dossier de sortie racine.")
@click.option("--ref", default="voix_ref.npz", help="Empreinte (cache).")
@click.option("--name", "names", multiple=True,
              help="Nom prononcé au lancement (répétable). Défaut: names.txt.")
@click.option("--threshold", default=None, type=float,
              help="Forcer le seuil (sinon auto-calibré).")
@click.option("--num-speakers", default=None, type=int)
@click.option("--pad", default=1.0, type=float)
@click.option("--min-len", default=3.0, type=float)
@click.option("--min-turn", default=1.5, type=float,
              help="Durée mini d'une prise de parole pour compter (écarte les parasites de diarisation).")
@click.option("--lookback", default=40.0, type=float,
              help="Durée max remontée pour l'annonce (s).")
@click.option("--launch-gap", default=10.0, type=float,
              help="Pause max tolérée dans un lancement (s).")
@click.option("--precut", default=5.0, type=float,
              help="Fenêtre pour caler une borne sur un cut plateau (s).")
@click.option("--end-trim", default=0.5, type=float,
              help="Marge de fin pour ne jamais montrer le retour plateau (s).")
@click.option("--fast", is_flag=True,
              help="Coupe rapide au plan près (défaut : à l'image près, plus net).")
@click.option("--shots", "shots_n", default=4, type=int,
              help="Nombre de screenshots 9:16 par passage.")
@click.option("--brand", default=None,
              help="Gabarit de vignette (logo brands/<nom>.png). "
                   "Défaut: le seul logo présent dans brands/.")
@click.option("--sharpen", default=screens.SHARPEN, type=float,
              help="Force du masque flou sur les vignettes (0 = désactivé).")
@click.option("--strip-furniture/--no-strip-furniture", default=None,
              help="Sort du cadre les bandes d'habillage qui touchent un bord. "
                   "Inutile quand l'effacement IA est actif : il reconstruit "
                   "déjà le décor, et rogner en plus ne fait que zoomer.")
@click.option("--retouche/--sans-retouche", "retouche", default=True,
              help="Retouche IA des vignettes : efface le bandeau et agrandit "
                   "proprement. Ignorée si les modèles ne sont pas installés "
                   "(director-cut models).")
@click.option("--screens/--no-screens", "screens_on", default=False,
              help="Vignettes 9:16 par passage. Désactivées par défaut : le "
                   "recadrage d'un 16:9 en 9:16 ne garde qu'un tiers de la "
                   "largeur, et la retouche IA charge lourdement la machine.")
@click.option("--no-mkv", is_flag=True, help="Pas de MKV sous-titré.")
@click.option("--no-transcript", is_flag=True, help="Pas de sous-titres (ni FR ni EN).")
@click.option("--whisper-size", default="small")
@click.option("--workers", default=3, type=int, help="Tâches en parallèle.")
@click.option("--hf-token", default=None, help="Défaut: .hf_token ou HF_TOKEN.")
def run_cmd(url, mode, merge_gap, out, ref, names, threshold, num_speakers, pad,
            min_len, min_turn, lookback, launch_gap, precut, end_trim, fast,
            shots_n, brand, sharpen, strip_furniture, retouche, screens_on, no_mkv,
            no_transcript, whisper_size, workers, hf_token):
    """Traite une URL ou un fichier vidéo local et découpe les passages.

    Usage : director-cut run "URL"   ou   director-cut run "/chemin/vers/video.mp4" """
    console = Console()
    ui.splash(console)

    os.makedirs(out, exist_ok=True)
    try:
        with lock.Lock(out):
            _run(console, url, mode, merge_gap, out, ref, names, threshold,
                 num_speakers, pad, min_len, min_turn, lookback, launch_gap,
                 precut, end_trim, fast, shots_n, brand, sharpen, strip_furniture,
                 retouche, screens_on, no_mkv, no_transcript, whisper_size,
                 workers, hf_token)
    except lock.Busy as e:
        raise click.ClickException(str(e))


def _run(console, url, mode, merge_gap, out, ref, names, threshold,
         num_speakers, pad, min_len, min_turn, lookback, launch_gap, precut,
         end_trim, fast, shots_n, brand, sharpen, strip_furniture, retouche, screens_on,
         no_mkv, no_transcript, whisper_size, workers, hf_token):
    workdir = os.getcwd()
    hf_token = _read_token(workdir, hf_token)
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
    names = _read_names(workdir, names)
    os.makedirs(out, exist_ok=True)

    template = None
    enhance_opts = None
    if screens_on:
        try:
            # On charge une première fois pour savoir ce que la retouche peut
            # faire, puis on tranche le rognage en fonction.
            template = brands.auto(brand, workdir)
        except ValueError as e:
            raise click.ClickException(str(e))
        if template:
            ui.info(console, f"vignettes : gabarit {template.name}")
        elif brands.available(workdir):
            ui.info(console, "vignettes sans logo (plusieurs gabarits "
                             "disponibles, précise --brand)")
        if retouche:
            enhance_opts = _retouche_opts(console, template)
        # Quand l'effacement IA est actif, le bandeau est reconstruit : rogner
        # les bandes en plus ne ferait que zoomer davantage pour rien.
        clean = bool(enhance_opts and enhance_opts.get("clean"))
        strip = (not clean) if strip_furniture is None else strip_furniture
        if strip and template:
            template = brands.auto(brand, workdir, strip=True)

    _ensure_reference(console, ref, workdir, hf_token)

    # Le dossier du run est fixé AVANT le téléchargement : la vidéo source et
    # l'audio y descendent. Partagés entre les runs, ils faisaient travailler
    # un run sur la source d'un autre — yt-dlp voyait un video.mp4 déjà là et
    # ne retéléchargeait pas.
    run_dir = os.path.join(out, f"extract_{mode}_{_guess_date(url)}")
    os.makedirs(run_dir, exist_ok=True)

    is_local = os.path.exists(url) and url.lower().endswith(download.VIDEO_EXTS)
    ui.step(console, 1, 6, "Vidéo locale…" if is_local else "Téléchargement…")
    video = download.get_video(url, os.path.join(run_dir, "raw"))

    ui.step(console, 2, 6, "Extraction audio…")
    wav = audio.extract_wav(video, os.path.join(run_dir, "audio.wav"))

    ui.step(console, 3, 6, "Diarisation (qui parle quand)…")
    diar = diarize.diarize(wav, hf_token, num_speakers)

    ui.step(console, 4, 6, "Identification de sa voix…")
    label, scores, her, thr = identify.find_her_segments(
        wav, diar, ref, threshold)
    if not label:
        ui.info(console, "scores: " +
                ", ".join(f"{k}={v:.2f}" for k, v in sorted(scores.items())))
        raise click.ClickException(
            "Voix non reconnue. Mets un meilleur sample.mp4 (où elle parle "
            "longtemps) et relance.")

    # Transcription FR (origine) + EN (traduction), une fois pour tout l'audio
    fr_tx = en_tx = None
    need_fr = (not no_transcript) or (mode == "chronique" and names)
    need_en = not no_transcript
    if need_fr or need_en:
        from . import transcribe
        ui.step(console, 5, 6, "Transcription (FR + EN)…")
        model = transcribe.load_model(whisper_size)
        with ui.make_progress(console) as prog:
            if need_fr:
                t = prog.add_task("FR", total=100)
                fr_tx = transcribe.transcribe_all(
                    wav, model=model, task="transcribe", lang="fr",
                    on_progress=lambda c, tot: prog.update(
                        t, completed=min(100, 100 * c / tot)))
                prog.update(t, completed=100)
            if need_en:
                t = prog.add_task("EN", total=100)
                en_tx = transcribe.transcribe_all(
                    wav, model=model, task="translate",
                    on_progress=lambda c, tot: prog.update(
                        t, completed=min(100, 100 * c / tot)))
                prog.update(t, completed=100)
    else:
        ui.step(console, 5, 6, "Transcription… (ignorée)")

    with console.status("[cyan]Détection des plans…[/]"):
        cuts = scenes.scene_cuts(video)

    # Bornes des passages
    name_status = None
    default_gap = {"chronique": 20.0, "reportage": 60.0, "jt": 300.0}[mode]
    gap = merge_gap if merge_gap is not None else default_gap

    # La diarisation lui attribue des miettes d'une fraction de seconde sur un
    # générique ou un fond sonore. Regroupées avec sa vraie prise de parole,
    # elles ramènent le début du passage des dizaines de secondes trop tôt.
    solid = segments.drop_short(her, min_turn)
    if solid:
        dropped = len(her) - len(solid)
        if dropped:
            ui.info(console, f"{dropped} fragment(s) de moins de {min_turn:g}s "
                             "écartés (parasites de diarisation)")
        her = solid

    if mode == "jt":
        merged = segments.merge_segments(her, gap)
        final = segments.snap_to_scenes(segments.pad_segments(merged, pad), cuts)
    else:
        blocks = segments.merge_segments(her, gap)
        all_turns = launch.turns(diar)
        final, validated_any = [], False
        for bs, be in blocks:
            s, e, validated = launch.build_span(
                mode, all_turns, label, bs, be, cuts=cuts,
                transcript=fr_tx, names=names, max_lookback=lookback,
                launch_gap=launch_gap, precut_window=precut, end_trim=end_trim)
            validated_any = validated_any or bool(validated)
            final.append((s, e))
        if names:
            name_status = ("nom détecté au lancement ✓" if validated_any
                           else "nom non vu (lancement pris quand même)")

    final = segments.drop_short(final, min_len)
    if not final:
        raise click.ClickException("Aucun passage retenu après filtrage.")

    total_kept = sum(e - s for s, e in final)
    ui.detection_summary(console, mode, label, scores[label], thr,
                         len(final), total_kept, name_status)

    # Un sous-dossier par type de sortie
    # Un dossier par type de sortie, et uniquement pour ce qu'on produit :
    # un dossier vide laisse croire que la sortie a échoué.
    kinds = ["passages", "audio"]
    if not no_transcript:
        kinds.append("srt")
    if screens_on:
        kinds.append("screens")
    if not no_mkv and not no_transcript:
        kinds.append("mkv")
    dirs = {k: os.path.join(run_dir, k) for k in kinds}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    def process(idx, seg):
        s, e = seg
        base = f"passage_{idx:02d}"
        made = {}
        made["mp4"] = cut.cut_one(
            video, s, e, os.path.join(dirs["passages"], base + ".mp4"),
            reencode=not fast)
        made["audio"] = audio.extract_clip_audio(
            video, s, e, os.path.join(dirs["audio"], base + ".m4a"))
        subs = []
        if fr_tx is not None:
            from . import transcribe
            subs.append((transcribe.clip_srt(
                fr_tx, s, e, os.path.join(dirs["srt"], base + ".fr.srt")), "fre"))
        if en_tx is not None:
            from . import transcribe
            subs.append((transcribe.clip_srt(
                en_tx, s, e, os.path.join(dirs["srt"], base + ".en.srt")), "eng"))
        if screens_on:
            screens.shots(video, s, e, dirs["screens"], base, n=shots_n,
                          brand=template, sharpen=sharpen,
                          enhance_opts=enhance_opts, cuts=cuts)
        if not no_mkv and subs:
            mux.mux_mkv(made["mp4"], subs,
                        os.path.join(dirs["mkv"], base + ".mkv"))
        return base

    if not os.path.exists(video):
        raise click.ClickException(
            f"La vidéo source a disparu pendant le run ({video}). "
            "Relance la commande : elle sera retéléchargée.")

    ui.step(console, 6, 6,
            f"Découpe + {' + '.join(sorted(k for k in dirs if k != 'passages'))}"
            f" ({len(final)} passage(s), {max(1, workers)} en //)…")
    done, failed = [], []
    with ui.make_progress(console) as prog:
        task = prog.add_task("passages", total=len(final))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = {ex.submit(process, i, seg): i
                    for i, seg in enumerate(final, 1)}
            for f in as_completed(futs):
                try:
                    done.append(f.result())
                except Exception as e:               # noqa: BLE001
                    # Un passage qui rate ne doit pas emporter les autres :
                    # on va au bout et on dit lesquels sont sortis.
                    failed.append((futs[f], e))
                prog.update(task, advance=1)

    for idx, err in sorted(failed):
        ui.info(console, f"[red]passage_{idx:02d} non produit[/] : {err}")
    if not done:
        raise click.ClickException(
            "Aucun passage n'a pu être produit. La cause est au-dessus ; si "
            "c'est un fichier introuvable, la vidéo source a disparu en cours "
            "de route — relance, elle sera retéléchargée.")

    console.print(f"\n[bold green]Terminé.[/] "
                  f"{len(done)}/{len(final)} passage(s) dans : [green]{run_dir}[/]")
    console.print("  " + "  ".join(f"{k}/" for k in sorted(dirs)))
    if not screens_on:
        ui.info(console, "vignettes 9:16 non produites (--screens pour les avoir)")


@cli.command("enroll")
@click.argument("samples", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--out", default="voix_ref.npz")
@click.option("--hf-token", default=None)
def enroll_cmd(samples, out, hf_token):
    """(Manuel) Force la création de l'empreinte. Un seul fichier = segment brut
    (diarisation auto) ; plusieurs = extraits déjà propres."""
    console = Console()
    hf_token = _read_token(os.getcwd(), hf_token)
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
    if len(samples) == 1:
        _, thr, dur, _ = enroll.enroll_from_chronique(
            samples[0], out, hf_token, diarize.diarize)
        console.print(f"Empreinte -> {out} · {dur:.0f}s · seuil {thr:.2f}")
    else:
        _, thr, n = enroll.enroll_from_clean_samples(list(samples), out)
        console.print(f"Empreinte -> {out} · {n} fenêtres · seuil {thr:.2f}")


@cli.command("models")
def models_cmd():
    """Télécharge une fois pour toutes les modèles de retouche des vignettes."""
    from . import enhance

    console = Console()
    for name in enhance.MODELS:
        if enhance.is_ready(name):
            console.print(f"[green]✓[/] {name} déjà installé")
            continue
        console.print(f"[cyan]»[/] téléchargement de {name}…")
        enhance.download(name)
        console.print(f"[green]✓[/] {name}")
    console.print(f"\nModèles dans [green]{enhance.CACHE}[/]. "
                  "Plus aucun appel réseau ensuite.")


if __name__ == "__main__":
    cli()
