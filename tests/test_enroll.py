import numpy as np

from director_cut import enroll


# --- calibrate_threshold --------------------------------------------------

def test_threshold_sits_between_her_voice_and_the_others():
    her = [0.80, 0.85, 0.90]
    others = [0.10, 0.15, 0.20]
    thr = enroll.calibrate_threshold(her, others)
    assert min(others) < thr < min(her)


def test_threshold_is_clamped_high_when_the_voices_never_overlap():
    # Sans plafond, un écart énorme donnerait un seuil inutilisable.
    thr = enroll.calibrate_threshold([0.95, 0.96, 0.97], [0.01, 0.02])
    assert thr <= 0.45


def test_threshold_is_clamped_low_when_the_voices_overlap():
    thr = enroll.calibrate_threshold([0.20, 0.21, 0.22], [0.19, 0.20, 0.21])
    assert thr >= 0.18


def test_threshold_without_other_voices_uses_her_own_variability():
    thr = enroll.calibrate_threshold([0.80, 0.82, 0.84, 0.86], [])
    assert 0.18 <= thr <= 0.45


def test_threshold_stays_in_range_on_a_degenerate_sample():
    thr = enroll.calibrate_threshold([0.5], [])
    assert 0.18 <= thr <= 0.45


# --- fenêtrage ------------------------------------------------------------

def test_windows_cuts_segments_into_fixed_size_chunks():
    wav = np.zeros(16000 * 12, dtype=np.float32)
    wins = enroll._windows(wav, 16000, [(0.0, 12.0)], win=4.0, hop=4.0)
    assert len(wins) == 3
    assert all(len(w) == 16000 * 4 for w in wins)


def test_windows_drops_chunks_that_are_too_short():
    wav = np.zeros(16000 * 5, dtype=np.float32)
    wins = enroll._windows(wav, 16000, [(0.0, 5.0)], win=4.0, hop=4.0, min_win=1.5)
    assert len(wins) == 1     # les 4s gardées, la dernière seconde jetée


def test_windows_on_an_empty_segment_list():
    assert enroll._windows(np.zeros(100), 16000, []) == []


# --- locuteur dominant ----------------------------------------------------

def test_dominant_label_is_the_one_who_speaks_the_longest():
    turns = [(0.0, 10.0, "A"), (10.0, 15.0, "B"), (20.0, 60.0, "B")]
    label, durations = enroll._dominant_label(turns)
    assert label == "B"
    assert durations == {"A": 10.0, "B": 45.0}


# --- sauvegarde de l'empreinte -------------------------------------------

def test_save_writes_the_reference_and_its_threshold(tmp_path):
    ref = np.ones(8, dtype=np.float32)
    path = enroll._save(str(tmp_path / "voix_ref"), ref, 0.33)
    assert path.endswith(".npz")
    data = np.load(path)
    assert np.allclose(data["ref"], ref)
    assert float(data["threshold"]) == np.float32(0.33)


def test_save_does_not_double_the_extension(tmp_path):
    path = enroll._save(str(tmp_path / "voix_ref.npz"), np.ones(4), 0.3)
    assert path.endswith("voix_ref.npz")


# --- enrôlement automatique depuis un sample brut ------------------------

def test_enroll_from_a_raw_sample_keeps_the_dominant_speaker(tmp_path,
                                                             monkeypatch):
    """Le sample contient 2 voix : l'empreinte doit être celle de la dominante,
    et le seuil doit séparer les deux."""
    import soundfile as sf

    sr = 16000
    sample = tmp_path / "sample.wav"
    sf.write(str(sample), np.zeros(sr * 30, dtype=np.float32), sr)

    turns = [(0.0, 20.0, "HER"), (20.0, 25.0, "HIM")]
    vectors = {"HER": np.array([1.0, 0.0], dtype=np.float32),
               "HIM": np.array([0.0, 1.0], dtype=np.float32)}

    def fake_extract_wav(src, out, sr=16000):
        sf.write(out, np.zeros(sr * 30, dtype=np.float32), sr)
        return out

    calls = {"n": 0}

    def fake_embed(wav, rate):
        # Les fenêtres arrivent dans l'ordre : d'abord elle, puis lui.
        calls["n"] += 1
        return vectors["HER"] if calls["n"] <= 5 else vectors["HIM"]

    monkeypatch.setattr(enroll, "extract_wav", fake_extract_wav)
    monkeypatch.setattr(enroll, "embed_array", fake_embed)

    out = str(tmp_path / "ref.npz")
    saved, thr, dur, n_other = enroll.enroll_from_chronique(
        str(sample), out, "token", lambda w, t, n: turns, str(tmp_path))

    data = np.load(saved)
    assert np.allclose(data["ref"], vectors["HER"])
    assert dur == 20.0
    assert n_other == 1
    assert 0.18 <= thr <= 0.45


def test_enroll_cleans_up_its_temporary_wav(tmp_path, monkeypatch):
    import soundfile as sf

    sr = 16000

    def fake_extract_wav(src, out, sr=16000):
        sf.write(out, np.zeros(sr * 10, dtype=np.float32), sr)
        return out

    monkeypatch.setattr(enroll, "extract_wav", fake_extract_wav)
    monkeypatch.setattr(enroll, "embed_array",
                        lambda w, r: np.array([1.0, 0.0], dtype=np.float32))
    enroll.enroll_from_chronique(
        "sample.mp4", str(tmp_path / "ref.npz"), "token",
        lambda w, t, n: [(0.0, 10.0, "HER")], str(tmp_path))
    assert not (tmp_path / "_enroll.wav").exists()
