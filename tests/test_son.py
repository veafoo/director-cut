"""Signature sonore : elle ne doit jamais gêner un run.


Aucun test ne fait sortir de son : le lancement est injecté.
"""
import pytest

from director_cut import son


def _mouchard():
    appels = []
    return appels, appels.append


def test_no_sound_when_asked_to_be_quiet():
    appels, lancer = _mouchard()
    assert son.jouer(actif=False, lancer=lancer) is False
    assert appels == []


def test_no_sound_outside_a_terminal():
    """Sortie redirigée, cron, script appelant : le son n'a rien à y faire."""
    appels, lancer = _mouchard()
    assert son.jouer(interactif=False, lancer=lancer) is False
    assert appels == []


def test_no_sound_when_the_machine_has_no_player(monkeypatch):
    monkeypatch.setattr(son, "lecteur", lambda: None)
    appels, lancer = _mouchard()
    assert son.jouer(lancer=lancer) is False
    assert appels == []


def test_a_personal_file_wins_over_the_default_signature(tmp_path, monkeypatch):
    perso = tmp_path / "jingle.mp3"
    perso.write_bytes(b"")
    monkeypatch.setattr(son, "lecteur", lambda: ["/usr/bin/afplay"])
    appels, lancer = _mouchard()
    assert son.jouer(str(tmp_path), lancer=lancer) is True
    assert appels[0][-1] == str(perso)


@pytest.mark.parametrize("nom", ["jingle.wav", "jingle-lou.m4a", "JINGLE.MP3"])
def test_the_personal_file_is_recognised_by_its_name(tmp_path, nom):
    (tmp_path / nom).write_bytes(b"")
    assert son.fichier_perso(str(tmp_path)) == str(tmp_path / nom)


def test_another_audio_file_is_not_taken_for_a_jingle(tmp_path):
    (tmp_path / "sample.mp4").write_bytes(b"")
    (tmp_path / "audio.wav").write_bytes(b"")
    assert son.fichier_perso(str(tmp_path)) is None


def test_a_failing_player_does_not_break_the_run(monkeypatch):
    """Le son est un agrément : son échec ne doit jamais remonter."""
    monkeypatch.setattr(son, "lecteur", lambda: ["/usr/bin/afplay"])
    monkeypatch.setattr(son, "fichier_perso", lambda w: "/tmp/x.wav")

    def casse(cmd):
        raise OSError("pas de carte son")

    assert son.jouer(lancer=casse) is False


def test_an_unreadable_folder_is_not_an_error():
    assert son.fichier_perso("/dossier/qui/n/existe/pas") is None
