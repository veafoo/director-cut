"""Revérification des tours : le groupe de voix n'est pas une preuve.

Sur un JT réel, une voix off de publicité s'est retrouvée dans le groupe de la
journaliste. Le groupe passait le seuil en moyenne, mais ce fragment étranger
prolongeait son passage au-delà du retour plateau.
"""
import numpy as np
import soundfile as sf

from director_cut import identify


def _wav(tmp_path, secondes=20.0, sr=16000):
    p = tmp_path / "a.wav"
    sf.write(p, np.zeros(int(secondes * sr), dtype="float32"), sr)
    return str(p)


def _ref(tmp_path):
    p = tmp_path / "ref.npz"
    np.savez(p, ref=np.array([1.0, 0.0]), threshold=0.45)
    return str(p)


def _scores(monkeypatch, valeurs):
    """Fait répondre la similarité voulue, tour après tour."""
    suite = iter(valeurs)
    monkeypatch.setattr(identify, "embed_array", lambda w, sr: next(suite))
    monkeypatch.setattr(identify, "cosine", lambda a, b: a)


def test_a_foreign_turn_is_dropped(tmp_path, monkeypatch):
    _scores(monkeypatch, [0.81, 0.27])       # elle, puis la voix off de pub
    gardes, ecartes = identify.verify_turns(
        _wav(tmp_path), [(1.0, 8.0), (10.0, 13.0)], _ref(tmp_path), 0.45)
    assert gardes == [(1.0, 8.0)]
    assert ecartes == [(10.0, 13.0)]


def test_her_own_turns_are_kept(tmp_path, monkeypatch):
    _scores(monkeypatch, [0.81, 0.62, 0.47])
    gardes, ecartes = identify.verify_turns(
        _wav(tmp_path), [(1.0, 4.0), (5.0, 9.0), (10.0, 14.0)],
        _ref(tmp_path), 0.45)
    assert len(gardes) == 3 and ecartes == []


def test_a_turn_too_short_to_judge_is_kept(tmp_path, monkeypatch):
    """Sous une seconde, une empreinte vocale est du bruit : on ne tranche pas."""
    _scores(monkeypatch, [0.81])             # une seule mesure : la courte est passée
    gardes, ecartes = identify.verify_turns(
        _wav(tmp_path), [(1.0, 1.4), (2.0, 6.0)], _ref(tmp_path), 0.45)
    assert (1.0, 1.4) in gardes
    assert ecartes == []


def test_nothing_to_verify_is_not_an_error(tmp_path):
    assert identify.verify_turns(_wav(tmp_path), [], _ref(tmp_path), 0.45) == ([], [])


def test_requiring_the_name_is_off_by_default():
    """Le nom n'est pas toujours prononcé au lancement : ça ne peut pas être
    une condition par défaut."""
    from director_cut import cli
    param = next(p for p in cli.run_cmd.params if p.name == "exiger_le_nom")
    assert param.default is False
