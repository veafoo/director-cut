import datetime
import os

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
