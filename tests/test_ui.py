"""Bandeau d'ouverture : mise en page, largeurs, nom du compte.

Un bandeau qui déborde de la fenêtre est illisible, et c'est la première chose
que voit l'utilisatrice. On vérifie donc surtout des largeurs.
"""
import types

import pytest
from rich.cells import cell_len
from rich.console import Console

from director_cut import ui


def render(width, jobs=None):
    console = Console(width=width, force_terminal=False, no_color=True)
    with console.capture() as cap:
        ui.splash(console, jobs)
    return cap.get()


@pytest.fixture
def compte(monkeypatch):
    """Remplace le compte de la machine par un compte connu."""
    def _set(gecos, login="jdupont"):
        import pwd
        monkeypatch.setattr(pwd, "getpwuid",
                            lambda _: types.SimpleNamespace(pw_gecos=gecos))
        monkeypatch.setattr(ui.getpass, "getuser", lambda: login)
    return _set


@pytest.mark.parametrize("width", [200, 120, 100, 92, 91, 70, 60])
def test_le_bandeau_ne_deborde_jamais_de_la_fenetre(width):
    for line in render(width, [{"mode": "reportage"}]).splitlines():
        assert cell_len(line) <= width


def test_deux_colonnes_quand_la_fenetre_est_large():
    # Le tout premier conseil doit se retrouver sur la ligne de bienvenue.
    lines = render(120, [{"mode": "reportage"}]).splitlines()
    assert any("Bienvenue" in l and "director-cut run" in l for l in lines)


def test_une_seule_colonne_quand_la_fenetre_est_etroite():
    lines = render(70, [{"mode": "reportage"}]).splitlines()
    assert not any("Bienvenue" in l and "director-cut run" in l for l in lines)
    bienvenue = next(i for i, l in enumerate(lines) if "Bienvenue" in l)
    conseils = next(i for i, l in enumerate(lines) if "Pour commencer" in l)
    assert bienvenue < conseils


def test_la_camera_tient_dans_la_colonne_de_gauche():
    for line in ui._CAMERA:
        assert cell_len(line) <= ui._LEFT - 2


def test_le_nom_vient_du_compte_de_la_machine(compte):
    compte("radwan mezzi")
    assert ui._user_name() == "Radwan"
    assert "Bienvenue, Radwan !" in render(120)


def test_le_prenom_garde_ses_majuscules(compte):
    compte("Jean-Marc Dupont")
    assert ui._user_name() == "Jean-Marc"


def test_repli_sur_l_identifiant_si_le_compte_n_a_pas_de_nom(compte):
    compte("", login="jdupont")
    assert ui._user_name() == "Jdupont"


def test_le_champ_gecos_peut_porter_autre_chose_que_le_nom(compte):
    # Sur certains systèmes : « Nom,bureau,tel,tel ».
    compte("Radwan Mezzi,Bureau 4,,")
    assert ui._user_name() == "Radwan"


def test_pas_de_nom_du_tout_ne_fait_pas_planter(monkeypatch):
    import pwd
    monkeypatch.setattr(pwd, "getpwuid", lambda _: (_ for _ in ()).throw(KeyError))
    monkeypatch.setattr(ui.getpass, "getuser",
                        lambda: (_ for _ in ()).throw(OSError))
    assert ui._user_name() == ""
    assert "Bienvenue !" in render(120)


@pytest.mark.parametrize("jobs,attendu", [
    (None, ""),
    ([], ""),
    ([{"mode": "reportage"}], "1 vidéo · reportage"),
    ([{"mode": "reportage"}, {"mode": "jt"}], "2 vidéos · reportage, jt"),
    # Deux fois le même mode ne s'écrit pas deux fois.
    ([{"mode": "jt"}, {"mode": "jt"}], "2 vidéos · jt"),
    ([{}], "1 vidéo"),
])
def test_ligne_des_videos_a_traiter(jobs, attendu):
    assert ui._jobs_line(jobs) == attendu


def test_le_dossier_courant_est_raccourci_avec_le_tilde(monkeypatch, tmp_path):
    monkeypatch.setattr(ui.os.path, "expanduser", lambda _: "/Users/x")
    monkeypatch.setattr(ui.os, "getcwd", lambda: "/Users/x/HQ/PROJECTS/director-cut")
    assert ui._cwd() == "~/HQ/PROJECTS/director-cut"
    monkeypatch.setattr(ui.os, "getcwd", lambda: "/opt/ailleurs")
    assert ui._cwd() == "/opt/ailleurs"


def test_le_bandeau_sort_sans_erreur_sans_paquet_installe(monkeypatch):
    """Dépôt cloné mais pas installé : pas de version, pas de plantage."""
    from importlib import metadata
    monkeypatch.setattr(metadata, "version",
                        lambda _: (_ for _ in ()).throw(
                            metadata.PackageNotFoundError))
    assert ui._version() == ""
    assert "director-cut" in render(120)
