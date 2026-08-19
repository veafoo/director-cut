"""_to_turns doit absorber les différences d'API entre pyannote 3.x et 4.x."""
import pytest

from director_cut import diarize


class Seg:
    def __init__(self, s, e):
        self.start, self.end = s, e


class Annotation3x:
    """pyannote 3.x : Annotation.itertracks(yield_label=True)."""

    def itertracks(self, yield_label=True):
        yield Seg(10.0, 20.0), "_", "SPEAKER_01"
        yield Seg(0.0, 5.0), "_", "SPEAKER_00"


class Annotation4x:
    """pyannote 4.x : itérable de (segment, ..., speaker)."""

    def __iter__(self):
        yield (Seg(10.0, 20.0), "_", "SPEAKER_01")
        yield (Seg(0.0, 5.0), "_", "SPEAKER_00")


class DiarizeOutput4x:
    """pyannote 4.x / community-1 : wrapper autour de l'annotation."""

    def __init__(self, ann):
        self.speaker_diarization = ann


EXPECTED = [(0.0, 5.0, "SPEAKER_00"), (10.0, 20.0, "SPEAKER_01")]


def test_to_turns_reads_pyannote_3x():
    assert diarize._to_turns(Annotation3x()) == EXPECTED


def test_to_turns_reads_pyannote_4x_wrapper():
    assert diarize._to_turns(DiarizeOutput4x(Annotation4x())) == EXPECTED


def test_to_turns_prefers_itertracks_when_the_wrapper_also_has_it():
    assert diarize._to_turns(DiarizeOutput4x(Annotation3x())) == EXPECTED


def test_to_turns_output_is_sorted_and_typed():
    turns = diarize._to_turns(Annotation3x())
    assert turns == sorted(turns)
    for s, e, label in turns:
        assert isinstance(s, float) and isinstance(e, float)
        assert isinstance(label, str)


def test_diarize_requires_a_token():
    try:
        diarize.diarize("x.wav", None)
    except RuntimeError as e:
        assert "Hugging Face" in str(e)
    else:
        raise AssertionError("un token manquant doit lever une RuntimeError")


# --- le modèle est partagé entre les vidéos -------------------------------

def test_the_pipeline_is_loaded_once_for_the_whole_batch(monkeypatch):
    """Sur un lot, recharger le modèle à chaque vidéo est du temps perdu."""
    charges = []

    class FakePipeline:
        def to(self, dev):
            return self

        def __call__(self, wav, **kw):
            return Annotation3x()

    def fake_from_pretrained(name, **kw):
        charges.append(name)
        return FakePipeline()

    import sys
    import types
    fake = types.ModuleType("pyannote.audio")
    fake.Pipeline = types.SimpleNamespace(from_pretrained=fake_from_pretrained)
    monkeypatch.setitem(sys.modules, "pyannote.audio", fake)
    monkeypatch.setattr(diarize, "_pipeline", None)

    for _ in range(3):
        diarize.diarize("x.wav", "token", show_progress=False)
    assert len(charges) == 1


def test_a_missing_token_is_still_refused(monkeypatch):
    monkeypatch.setattr(diarize, "_pipeline", None)
    with pytest.raises(RuntimeError, match="Hugging Face"):
        diarize.load_pipeline(None)


def test_liberer_la_diarisation_vide_le_cache():
    """Le pipeline doit vraiment être lâché : c'est tout l'intérêt."""
    diarize._pipeline = object()
    diarize.unload()
    assert diarize._pipeline is None


def test_liberer_sans_rien_de_charge_ne_fait_rien():
    diarize._pipeline = None
    diarize.unload()
    assert diarize._pipeline is None
