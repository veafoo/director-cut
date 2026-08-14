import numpy as np
import pytest
import soundfile as sf

from director_cut import identify

HER = np.array([1.0, 0.0], dtype=np.float32)
HIM = np.array([0.0, 1.0], dtype=np.float32)

TURNS = [
    (0.0, 10.0, "SPEAKER_00"),
    (10.0, 40.0, "SPEAKER_01"),
    (40.0, 45.0, "SPEAKER_00"),
]


@pytest.fixture
def wav(tmp_path):
    path = tmp_path / "audio.wav"
    sf.write(str(path), np.zeros(16000 * 60, dtype=np.float32), 16000)
    return str(path)


@pytest.fixture
def ref_npz(tmp_path):
    path = tmp_path / "voix_ref.npz"
    np.savez(str(path), ref=HER, threshold=np.float32(0.30))
    return str(path)


@pytest.fixture
def voices(monkeypatch):
    """SPEAKER_01 = elle, les autres = quelqu'un d'autre."""
    order = []

    def fake_embed(chunk, sr):
        return HER if order.pop(0) == "her" else HIM

    def install(sequence):
        order.extend(sequence)
        monkeypatch.setattr(identify, "embed_array", fake_embed)
    return install


def test_load_reference_reads_the_vector_and_its_threshold(ref_npz):
    ref, thr = identify.load_reference(ref_npz)
    assert np.allclose(ref, HER)
    assert thr == pytest.approx(0.30, abs=1e-6)


def test_load_reference_accepts_a_legacy_npy(tmp_path):
    path = tmp_path / "old.npy"
    np.save(str(path), HER)
    ref, thr = identify.load_reference(str(path))
    assert np.allclose(ref, HER)
    assert thr is None


def test_find_her_segments_picks_the_matching_speaker(wav, ref_npz, voices):
    voices(["him", "her"])       # SPEAKER_00 puis SPEAKER_01
    label, scores, segs, thr = identify.find_her_segments(wav, TURNS, ref_npz)
    assert label == "SPEAKER_01"
    assert segs == [(10.0, 40.0)]
    assert scores["SPEAKER_01"] > scores["SPEAKER_00"]


def test_find_her_segments_returns_all_her_turns_sorted(wav, ref_npz, voices):
    turns = TURNS + [(50.0, 55.0, "SPEAKER_01")]
    voices(["him", "her"])
    _, _, segs, _ = identify.find_her_segments(wav, turns, ref_npz)
    assert segs == [(10.0, 40.0), (50.0, 55.0)]


def test_find_her_segments_uses_the_calibrated_threshold(wav, ref_npz, voices):
    voices(["him", "her"])
    *_, thr = identify.find_her_segments(wav, TURNS, ref_npz)
    assert thr == pytest.approx(0.30, abs=1e-6)


def test_an_explicit_threshold_wins_over_the_calibrated_one(wav, ref_npz, voices):
    voices(["him", "her"])
    *_, thr = identify.find_her_segments(wav, TURNS, ref_npz, threshold=0.42)
    assert thr == 0.42


def test_nobody_matches_when_every_score_is_below_the_threshold(wav, ref_npz,
                                                               voices):
    voices(["him", "him"])
    label, scores, segs, _ = identify.find_her_segments(wav, TURNS, ref_npz)
    assert label is None
    assert segs == []
    assert set(scores) == {"SPEAKER_00", "SPEAKER_01"}   # scores rendus au user


def test_no_speaker_at_all(wav, ref_npz):
    label, scores, segs, _ = identify.find_her_segments(wav, [], ref_npz)
    assert (label, scores, segs) == (None, {}, [])


def test_enrollment_audio_is_capped(wav, ref_npz, monkeypatch):
    """On ne pousse pas 20 minutes de voix dans le modèle d'empreinte."""
    seen = []

    def fake_embed(chunk, sr):
        seen.append(len(chunk) / sr)
        return HER

    monkeypatch.setattr(identify, "embed_array", fake_embed)
    turns = [(float(i * 5), float(i * 5 + 5), "SPEAKER_01") for i in range(10)]
    identify.find_her_segments(wav, turns, ref_npz, max_enroll_sec=20)
    assert seen[0] <= 25.0
