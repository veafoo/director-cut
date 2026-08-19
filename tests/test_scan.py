"""Repérage grossier de sa voix : ce qu'on garde, et quand on renonce.

Le risque de cette optimisation n'est pas d'être lente, c'est de rater un
passage. Les tests portent donc surtout sur le filet.
"""
import numpy as np
import soundfile as sf

from director_cut import scan


def _wav(tmp_path, secondes, sr=16000):
    p = tmp_path / "a.wav"
    sf.write(p, np.zeros(int(secondes * sr), dtype="float32"), sr)
    return str(p)


def _sondes(monkeypatch, gagnantes):
    """Fait répondre « c'est elle » sur les sondes d'indices donnés."""
    compteur = {"i": -1}

    def faux_embed(bloc, sr):
        compteur["i"] += 1
        return compteur["i"]

    monkeypatch.setattr(scan.embeddings, "embed_array", faux_embed)
    monkeypatch.setattr(scan.embeddings, "cosine",
                        lambda a, b: 1.0 if a in gagnantes else 0.0)


def test_only_the_area_around_a_hit_is_kept(tmp_path, monkeypatch):
    _sondes(monkeypatch, {2})            # sonde n°2 -> 16 s à 20 s
    regions = scan.voice_regions(_wav(tmp_path, 60.0), None, 0.5, margin=10.0)
    assert regions == [(6.0, 30.0)]


def test_the_margin_never_goes_before_the_start(tmp_path, monkeypatch):
    _sondes(monkeypatch, {0})
    regions = scan.voice_regions(_wav(tmp_path, 60.0), None, 0.5, margin=30.0)
    assert regions[0][0] == 0.0


def test_the_margin_never_goes_past_the_end(tmp_path, monkeypatch):
    _sondes(monkeypatch, {6})            # 48 s à 52 s sur 60 s
    regions = scan.voice_regions(_wav(tmp_path, 60.0), None, 0.5, margin=30.0)
    assert regions[-1][1] == 60.0


def test_nearby_hits_become_one_area(tmp_path, monkeypatch):
    _sondes(monkeypatch, {2, 3})
    regions = scan.voice_regions(_wav(tmp_path, 60.0), None, 0.5, margin=10.0)
    assert len(regions) == 1


def test_the_scan_threshold_is_lower_than_the_identification_one(tmp_path,
                                                                 monkeypatch):
    """Mieux vaut garder une zone pour rien que d'en manquer une."""
    monkeypatch.setattr(scan.embeddings, "embed_array", lambda b, sr: 0)
    # Score juste sous le seuil demandé, mais au-dessus du seuil abaissé.
    monkeypatch.setattr(scan.embeddings, "cosine", lambda a, b: 0.45)
    regions = scan.voice_regions(_wav(tmp_path, 30.0), None, 0.5)
    assert regions, "un score légèrement sous le seuil doit quand même être exploré"


def test_no_hit_at_all_means_no_area(tmp_path, monkeypatch):
    _sondes(monkeypatch, set())
    assert scan.voice_regions(_wav(tmp_path, 60.0), None, 0.5) == []


# --- le filet -------------------------------------------------------------


def test_finding_nothing_falls_back_to_the_full_source():
    """Le balayage est grossier : son silence ne prouve pas qu'elle est absente."""
    assert scan.vaut_le_coup([], 3600.0) is False


def test_finding_almost_everything_falls_back_too():
    # 80 % de la source retenue : découper ne rapporte plus rien.
    assert scan.vaut_le_coup([(0.0, 2880.0)], 3600.0) is False


def test_a_few_areas_are_worth_it():
    assert scan.vaut_le_coup([(0.0, 300.0), (1000.0, 1300.0)], 3600.0) is True


def test_coverage_of_an_empty_scan_is_none():
    assert scan.couverture([], 3600.0) == 0.0


# --- recollement des identités entre zones --------------------------------


def test_the_same_voice_keeps_one_identity_across_areas():
    """Sans ça, le présentateur serait vu comme dix personnes différentes.

    Chaque zone est diarisée à part : son SPEAKER_00 n'a aucun rapport avec
    celui de la zone suivante. La découpe, elle, reconnaît le présentateur à sa
    présence d'un bout à l'autre du journal."""
    connus = {}
    a = np.array([1.0, 0.0])
    presque_a = np.array([0.99, 0.14])
    autre = np.array([0.0, 1.0])
    n1 = scan._rattacher(a, connus)
    n2 = scan._rattacher(presque_a, connus)      # même voix, autre zone
    n3 = scan._rattacher(autre, connus)
    assert n1 == n2
    assert n3 != n1
    assert len(connus) == 2


def test_a_speaker_without_usable_audio_is_dropped():
    assert scan._rattacher(None, {}) is None


def test_area_times_are_put_back_on_the_source_timeline(tmp_path, monkeypatch):
    wav = _wav(tmp_path, 60.0)
    monkeypatch.setattr(scan.audio, "extract_wav_span",
                        lambda w, d, f, out, **kw: (sf.write(
                            out, np.zeros(16000, dtype="float32"), 16000), out)[1])
    monkeypatch.setattr(scan, "_empreinte_locuteur",
                        lambda *a, **kw: np.array([1.0, 0.0]))
    tours = scan.diarize_regions(
        wav, [(100.0, 130.0), (500.0, 530.0)],
        lambda chemin: [(2.0, 5.0, "SPEAKER_00")], str(tmp_path))
    assert [(s, e) for s, e, _ in tours] == [(102.0, 105.0), (502.0, 505.0)]
    # Même voix des deux côtés : une seule identité.
    assert len({l for _, _, l in tours}) == 1
