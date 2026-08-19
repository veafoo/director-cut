from director_cut import transcribe

TRANSCRIPT = [
    (0.0, 5.0, "avant le passage"),
    (28.0, 32.0, "à cheval sur le début"),
    (40.0, 45.0, "en plein milieu"),
    (58.0, 62.0, "à cheval sur la fin"),
    (80.0, 85.0, "après le passage"),
    (42.0, 43.0, ""),
]


def _read(path):
    return open(path, encoding="utf-8").read()


def test_srt_time_formats_hours_minutes_millis():
    assert transcribe._srt_time(3661.5) == "01:01:01,500"


def test_srt_time_zero_and_negative_are_clamped():
    assert transcribe._srt_time(0.0) == "00:00:00,000"
    assert transcribe._srt_time(-3.0) == "00:00:00,000"


def test_clip_srt_keeps_only_overlapping_segments(tmp_path):
    out = transcribe.clip_srt(TRANSCRIPT, 30.0, 60.0, str(tmp_path / "p.srt"))
    text = _read(out)
    assert "à cheval sur le début" in text
    assert "en plein milieu" in text
    assert "à cheval sur la fin" in text
    assert "avant le passage" not in text
    assert "après le passage" not in text


def test_clip_srt_rebases_timestamps_to_zero(tmp_path):
    out = transcribe.clip_srt(TRANSCRIPT, 30.0, 60.0, str(tmp_path / "p.srt"))
    lines = _read(out).splitlines()
    # 1er sous-titre : 28->32 devient 0 -> 2s (le mp4 du passage démarre à 0)
    assert lines[0] == "1"
    assert lines[1] == "00:00:00,000 --> 00:00:02,000"


def test_clip_srt_numbers_entries_sequentially(tmp_path):
    out = transcribe.clip_srt(TRANSCRIPT, 30.0, 60.0, str(tmp_path / "p.srt"))
    indexes = [l for l in _read(out).splitlines() if l.isdigit()]
    assert indexes == ["1", "2", "3"]


def test_clip_srt_drops_empty_text(tmp_path):
    out = transcribe.clip_srt([(42.0, 43.0, "")], 30.0, 60.0,
                              str(tmp_path / "p.srt"))
    assert _read(out) == ""


def test_clip_srt_gives_every_subtitle_a_visible_duration(tmp_path):
    # Segment qui finit pile au début du passage -> durée nulle interdite.
    out = transcribe.clip_srt([(29.0, 30.05, "flash")], 30.0, 60.0,
                              str(tmp_path / "p.srt"))
    start, end = _read(out).splitlines()[1].split(" --> ")
    assert start != end


def test_transcribe_all_normalizes_segments_and_reports_progress():
    class Seg:
        def __init__(self, s, e, t):
            self.start, self.end, self.text = s, e, t

    class Info:
        duration = 10.0

    class Model:
        def __init__(self):
            self.kwargs = None

        def transcribe(self, wav, **kwargs):
            self.kwargs = kwargs
            return iter([Seg(0.0, 5.0, " bonjour "), Seg(5.0, 10.0, "ça va")]), Info()

    model = Model()
    seen = []
    out = transcribe.transcribe_all("x.wav", model=model,
                                    on_progress=lambda c, t: seen.append((c, t)))
    assert out == [(0.0, 5.0, "bonjour"), (5.0, 10.0, "ça va")]
    assert seen == [(5.0, 10.0), (10.0, 10.0)]
    assert model.kwargs["task"] == "transcribe"
    assert model.kwargs["language"] == "fr"


def test_transcribe_all_translation_does_not_force_the_source_language():
    class Info:
        duration = 0.0

    class Model:
        def __init__(self):
            self.kwargs = None

        def transcribe(self, wav, **kwargs):
            self.kwargs = kwargs
            return iter([]), Info()

    model = Model()
    transcribe.transcribe_all("x.wav", model=model, task="translate")
    assert model.kwargs["task"] == "translate"
    assert "language" not in model.kwargs


def test_the_whisper_model_is_loaded_once_per_size(monkeypatch):
    """Sur un lot de vidéos, un seul chargement par taille de modèle."""
    charges = []

    class FakeWhisper:
        def __init__(self, size, **kw):
            charges.append(size)

    import sys
    import types
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = FakeWhisper
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    monkeypatch.setattr(transcribe, "_models", {})

    for _ in range(3):
        transcribe.load_model("small")
    transcribe.load_model("large-v3")
    assert charges == ["small", "large-v3"]


# --- ne transcrire que le voisinage des passages --------------------------


def test_windows_cover_what_the_borders_will_look_for():
    # La marge doit précéder le passage : c'est là que se trouve l'annonce.
    assert transcribe.windows_around([(100.0, 160.0)], 90.0) == [(10.0, 250.0)]


def test_windows_never_start_before_the_beginning():
    assert transcribe.windows_around([(10.0, 20.0)], 90.0) == [(0.0, 110.0)]


def test_overlapping_windows_are_merged():
    """Deux passages proches ne doivent pas faire transcrire deux fois."""
    assert transcribe.windows_around([(100.0, 160.0), (200.0, 240.0)], 90.0) \
        == [(10.0, 330.0)]


def test_distant_passages_keep_their_own_window():
    fenetres = transcribe.windows_around([(100.0, 160.0), (900.0, 940.0)], 90.0)
    assert len(fenetres) == 2


def test_no_passage_no_transcription():
    assert transcribe.windows_around([], 90.0) == []


def test_window_times_are_put_back_on_the_source_timeline(monkeypatch):
    """Le modèle rend des temps relatifs à la fenêtre qu'on lui a donnée.

    Sans recalage, tous les sous-titres seraient décalés du début de la fenêtre
    — et les bornes calculées sur le mauvais texte."""
    from director_cut import audio

    def faux_decoupage(wav, debut, fin, out, **kw):
        open(out, "w").close()
        return out

    monkeypatch.setattr(audio, "extract_wav_span", faux_decoupage)
    monkeypatch.setattr(transcribe, "transcribe_all",
                        lambda path, **kw: [(0.0, 2.0, "un"), (2.0, 4.0, "deux")])

    out = transcribe.transcribe_windows(
        "source.wav", [(100.0, 110.0), (300.0, 310.0)], model=object())
    assert out == [(100.0, 102.0, "un"), (102.0, 104.0, "deux"),
                   (300.0, 302.0, "un"), (302.0, 304.0, "deux")]


def test_progress_is_reported_on_the_audio_actually_done(monkeypatch):
    from director_cut import audio

    monkeypatch.setattr(audio, "extract_wav_span",
                        lambda w, d, f, out, **kw: (open(out, "w").close(), out)[1])
    monkeypatch.setattr(transcribe, "transcribe_all", lambda path, **kw: [])
    vus = []
    transcribe.transcribe_windows("s.wav", [(0.0, 10.0), (50.0, 70.0)],
                                  model=object(),
                                  on_progress=lambda c, t: vus.append((c, t)))
    assert vus[-1] == (30.0, 30.0)
