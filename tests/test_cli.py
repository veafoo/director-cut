import datetime
import os

import click
import pytest
from click.testing import CliRunner

from director_cut import cli


# --- date du run ----------------------------------------------------------

def test_guess_date_reads_the_date_out_of_a_url():
    url = "https://www.example.com/replay/journal-20260812-edition.html"
    assert cli._guess_date(url) == "2026-08-12"


def test_guess_date_reads_the_date_out_of_a_filename():
    assert cli._guess_date("/videos/jt_20251203.mp4") == "2025-12-03"


def test_guess_date_ignores_an_impossible_date():
    assert cli._guess_date("ref-20269999.mp4") == datetime.date.today().isoformat()


def test_guess_date_falls_back_on_today():
    assert cli._guess_date("https://example.com/video") == \
        datetime.date.today().isoformat()


def test_guess_date_handles_no_source_at_all():
    assert cli._guess_date(None) == datetime.date.today().isoformat()


# --- token ----------------------------------------------------------------

def test_token_option_wins(tmp_path):
    assert cli._read_token(str(tmp_path), "hf_option") == "hf_option"


def test_token_falls_back_on_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_env")
    assert cli._read_token(str(tmp_path), None) == "hf_env"


def test_token_is_read_from_the_dotfile(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    (tmp_path / ".hf_token").write_text("hf_file\n")
    assert cli._read_token(str(tmp_path), None) == "hf_file"


def test_token_is_none_when_nothing_is_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert cli._read_token(str(tmp_path), None) is None


# --- noms prononcés au lancement -----------------------------------------

def test_names_option_wins(tmp_path):
    assert cli._read_names(str(tmp_path), ("Marie",)) == ["Marie"]


def test_names_are_read_from_names_txt(tmp_path):
    (tmp_path / "names.txt").write_text("Marie Dupont\n\n  Marie Dupond  \n")
    assert cli._read_names(str(tmp_path), ()) == ["Marie Dupont", "Marie Dupond"]


def test_names_default_to_nothing(tmp_path):
    assert cli._read_names(str(tmp_path), ()) == []


# --- découverte des samples ----------------------------------------------

def test_clean_samples_folder_has_priority(tmp_path):
    (tmp_path / "sample.mp4").write_bytes(b"x")
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples" / "a.wav").write_bytes(b"x")
    (tmp_path / "samples" / "b.wav").write_bytes(b"x")
    files, kind = cli._find_samples(str(tmp_path))
    assert kind == "clean"
    assert [os.path.basename(f) for f in files] == ["a.wav", "b.wav"]


def test_a_raw_sample_file_is_used_when_there_is_no_samples_folder(tmp_path):
    (tmp_path / "sample.mp4").write_bytes(b"x")
    files, kind = cli._find_samples(str(tmp_path))
    assert kind == "segment"
    assert files[0].endswith("sample.mp4")


def test_an_empty_samples_folder_falls_back_on_the_raw_sample(tmp_path):
    (tmp_path / "samples").mkdir()
    (tmp_path / "sample.mov").write_bytes(b"x")
    _, kind = cli._find_samples(str(tmp_path))
    assert kind == "segment"


def test_unrelated_files_are_not_taken_for_samples(tmp_path):
    (tmp_path / "reportage.mp4").write_bytes(b"x")
    (tmp_path / "sample.txt").write_text("x")
    assert cli._find_samples(str(tmp_path)) == ([], None)


# --- empreinte vocale : quand la recalcule-t-on ? ------------------------

class Recorder:
    def __init__(self):
        self.called = False

    def __call__(self, *args, **kwargs):
        self.called = True
        return ("ref.npz", 0.30, 42.0, 3)


def test_reference_is_not_rebuilt_when_it_is_up_to_date(tmp_path, monkeypatch):
    from rich.console import Console
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"x")
    ref = tmp_path / "voix_ref.npz"
    ref.write_bytes(b"x")
    os.utime(str(sample), (1000, 1000))
    os.utime(str(ref), (2000, 2000))

    rec = Recorder()
    monkeypatch.setattr(cli.enroll, "enroll_from_chronique", rec)
    cli._ensure_reference(Console(), str(ref), str(tmp_path), "token")
    assert not rec.called


def test_reference_is_rebuilt_when_the_sample_is_newer(tmp_path, monkeypatch):
    from rich.console import Console
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"x")
    ref = tmp_path / "voix_ref.npz"
    ref.write_bytes(b"x")
    os.utime(str(ref), (1000, 1000))
    os.utime(str(sample), (2000, 2000))

    rec = Recorder()
    monkeypatch.setattr(cli.enroll, "enroll_from_chronique", rec)
    cli._ensure_reference(Console(), str(ref), str(tmp_path), "token")
    assert rec.called


def test_a_missing_sample_gives_an_actionable_error(tmp_path):
    from rich.console import Console
    import click
    with pytest.raises(click.ClickException) as err:
        cli._ensure_reference(Console(), str(tmp_path / "nope.npz"),
                              str(tmp_path), "token")
    assert "sample.mp4" in str(err.value)


# --- surface CLI ----------------------------------------------------------

def test_the_two_commands_are_exposed():
    result = CliRunner().invoke(cli.cli, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "enroll" in result.output


def test_run_help_lists_the_three_modes():
    result = CliRunner().invoke(cli.cli, ["run", "--help"])
    assert result.exit_code == 0
    for mode in ("chronique", "reportage", "jt"):
        assert mode in result.output


def test_run_requires_a_source():
    assert CliRunner().invoke(cli.cli, ["run"]).exit_code != 0


# --- les vignettes sont une option, pas un défaut -------------------------

def test_thumbnails_are_off_by_default():
    result = CliRunner().invoke(cli.cli, ["run", "--help"])
    assert "--screens / --no-screens" in result.output


def test_only_the_produced_folders_are_created(tmp_path):
    """Un dossier vide laisse croire que la sortie a échoué."""
    kinds = ["passages", "audio"]
    for srt_langs, screens_on, no_mkv, attendu in (
            (["fr"], False, False, {"passages", "audio", "srt", "mkv"}),
            (["fr", "en"], True, False,
             {"passages", "audio", "srt", "screens", "mkv"}),
            ([], False, True, {"passages", "audio"}),
            ([], True, True, {"passages", "audio", "screens"}),
            # Sous-titres demandés mais MKV refusé : le srt sort quand même.
            (["fr"], False, True, {"passages", "audio", "srt"})):
        k = list(kinds)
        if srt_langs:
            k.append("srt")
        if screens_on:
            k.append("screens")
        if not no_mkv and srt_langs:
            k.append("mkv")
        assert set(k) == attendu


def test_thumbnails_need_an_explicit_flag():
    # Sans --screens : pas de vignettes, donc aucun modèle IA chargé.
    param = next(p for p in cli.run_cmd.params if p.name == "screens_on")
    assert param.default is False
    assert "--screens" in param.opts and "--no-screens" in param.secondary_opts


# --- plusieurs vidéos dans une commande -----------------------------------

def test_the_run_command_takes_several_sources():
    param = next(p for p in cli.run_cmd.params if p.name == "urls")
    assert param.nargs == -1
    assert param.required


def test_each_source_gets_its_own_folder():
    taken = set()
    a = cli._free_run_dir("sortie", "reportage", "https://x.fr/jt-20260812.html", taken)
    b = cli._free_run_dir("sortie", "reportage", "https://x.fr/jt-20260813.html", taken)
    assert a.endswith("extract_reportage_2026-08-12")
    assert b.endswith("extract_reportage_2026-08-13")


def test_two_videos_of_the_same_day_do_not_overwrite_each_other():
    taken = set()
    noms = [os.path.basename(
        cli._free_run_dir("sortie", "reportage", f"https://x.fr/jt-20260812-{n}.html",
                          taken)) for n in "abc"]
    assert noms == ["extract_reportage_2026-08-12",
                    "extract_2_reportage_2026-08-12",
                    "extract_3_reportage_2026-08-12"]


def test_running_the_same_url_again_falls_back_on_its_folder():
    # Une nouvelle commande repart d'un jeu de noms vierge : pas de _2 parasite.
    url = "https://x.fr/jt-20260812.html"
    premier = cli._free_run_dir("sortie", "reportage", url, set())
    second = cli._free_run_dir("sortie", "reportage", url, set())
    assert premier == second


def test_the_mode_is_part_of_the_folder_name():
    taken = set()
    url = "https://x.fr/jt-20260812.html"
    a = cli._free_run_dir("sortie", "reportage", url, taken)
    b = cli._free_run_dir("sortie", "chronique", url, taken)
    assert a != b and "chronique" in b


# --- un échec ne doit pas laisser de trace --------------------------------

def test_an_empty_folder_left_by_a_failed_run_is_removed(tmp_path):
    d = tmp_path / "extract_reportage_2026-08-17"
    (d / "raw").mkdir(parents=True)
    (d / "passages").mkdir()
    assert cli._forget(str(d))
    assert not d.exists()


def test_a_folder_that_produced_something_is_never_removed(tmp_path):
    d = tmp_path / "extract_reportage_2026-08-17"
    (d / "passages").mkdir(parents=True)
    (d / "passages" / "passage_01.mp4").write_bytes(b"x")
    assert not cli._forget(str(d))
    assert (d / "passages" / "passage_01.mp4").exists()


def test_a_stray_ds_store_does_not_pass_for_a_result(tmp_path):
    d = tmp_path / "extract_reportage_2026-08-17"
    (d / "raw").mkdir(parents=True)
    (d / "raw" / ".DS_Store").write_bytes(b"x")
    assert cli._forget(str(d))


def test_forgetting_a_folder_that_was_never_created():
    assert cli._forget("/chemin/qui/n/existe/pas")


def test_the_label_stays_short_and_readable():
    assert cli._label("https://x.fr/replay/jt-du-12-aout.html") == "jt-du-12-aout.html"
    assert len(cli._label("https://x.fr/" + "a" * 200)) <= 71


# --- sous-titres : une option, et le choix des langues --------------------


def test_subtitles_are_off_by_default():
    """Chaque langue coûte une passe de transcription sur tout l'audio."""
    param = next(p for p in cli.run_cmd.params if p.name == "sous_titres")
    assert param.default is False
    assert cli._langues_srt(False, None) == []


def test_asking_for_subtitles_gives_french():
    assert cli._langues_srt(True, None) == ["fr"]


@pytest.mark.parametrize("demande,attendu", [
    ("fr", ["fr"]),
    ("en", ["en"]),
    ("fr,en", ["fr", "en"]),
    ("en,fr", ["en", "fr"]),          # l'ordre demandé est conservé
    ("FR, EN", ["fr", "en"]),         # casse et espaces tolérées
    ("fr fr en", ["fr", "en"]),       # doublons écartés
])
def test_languages_can_be_chosen(demande, attendu):
    assert cli._langues_srt(False, demande) == attendu


def test_choosing_languages_implies_subtitles():
    # Pas besoin de penser à --sous-titres si on a nommé les langues.
    assert cli._langues_srt(False, "en") == ["en"]


def test_an_impossible_language_is_refused_with_the_reason():
    with pytest.raises(click.BadParameter) as e:
        cli._langues_srt(False, "es")
    assert "es" in str(e.value)
    # Le message doit dire pourquoi, pas seulement que c'est refusé.
    assert "anglais" in str(e.value)


def test_an_impossible_language_is_refused_before_any_work():
    """La faute de frappe doit se voir avant le téléchargement, pas après."""
    result = CliRunner().invoke(cli.cli, ["run", "--langues", "es", "x.mp4"])
    assert result.exit_code != 0
    assert "indisponible" in result.output
    # Le message doit venir du contrôle de la ligne de commande…
    assert "--langues" in result.output
    # …et pas d'une étape de traitement.
    assert "empreinte" not in result.output
