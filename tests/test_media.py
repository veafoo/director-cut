"""Modules qui pilotent ffmpeg : on vérifie les commandes construites, pas
ffmpeg lui-même (les vrais encodages sont validés sur un run réel)."""
import subprocess

import pytest

from director_cut import audio, cut, ff, mux, scenes


@pytest.fixture
def ffmpeg(monkeypatch):
    """Capture les commandes ffmpeg de tous les modules média."""
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(ff, "run", fake_run)
    return calls


def _arg_after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


# --- audio ----------------------------------------------------------------

def test_extract_wav_asks_for_mono_16k_without_video(ffmpeg):
    audio.extract_wav("in.mp4", "out.wav")
    cmd = ffmpeg[0]
    assert _arg_after(cmd, "-ac") == "1"
    assert _arg_after(cmd, "-ar") == "16000"
    assert "-vn" in cmd


def test_extract_clip_audio_uses_the_passage_bounds(ffmpeg):
    audio.extract_clip_audio("in.mp4", 10.0, 25.5, "out.m4a")
    cmd = ffmpeg[0]
    assert _arg_after(cmd, "-ss") == "10.000"
    assert _arg_after(cmd, "-t") == "15.500"
    assert _arg_after(cmd, "-c:a") == "aac"


# --- découpe --------------------------------------------------------------

def test_cut_one_reencodes_by_default_for_a_frame_accurate_cut(ffmpeg):
    cut.cut_one("in.mp4", 10.0, 20.0, "out.mp4")
    cmd = ffmpeg[0]
    # -ss APRÈS -i : ffmpeg décode puis coupe -> bornes à l'image près
    assert cmd.index("-i") < cmd.index("-ss")
    assert _arg_after(cmd, "-c:v") == "libx264"
    assert _arg_after(cmd, "-to") == "20.000"


def test_cut_one_fast_mode_copies_the_streams(ffmpeg):
    cut.cut_one("in.mp4", 10.0, 20.0, "out.mp4", reencode=False)
    cmd = ffmpeg[0]
    # -ss AVANT -i : seek rapide, mais cale sur keyframe
    assert cmd.index("-ss") < cmd.index("-i")
    assert _arg_after(cmd, "-c") == "copy"
    assert _arg_after(cmd, "-t") == "10.000"


def test_cut_segments_produces_one_file_per_passage(ffmpeg, tmp_path):
    clips = cut.cut_segments("in.mp4", [(0.0, 5.0), (10.0, 15.0)],
                             str(tmp_path), concat=False)
    assert [c.split("/")[-1] for c in clips] == ["passage_01.mp4", "passage_02.mp4"]
    assert len(ffmpeg) == 2


def test_cut_segments_can_concatenate(ffmpeg, tmp_path):
    clips = cut.cut_segments("in.mp4", [(0.0, 5.0), (10.0, 15.0)],
                             str(tmp_path), concat=True)
    assert clips[-1].endswith("passage_complet.mp4")
    assert "concat" in ffmpeg[-1]


def test_cut_segments_reports_progress(ffmpeg, tmp_path):
    seen = []
    cut.cut_segments("in.mp4", [(0.0, 5.0), (10.0, 15.0)], str(tmp_path),
                     concat=False, on_progress=lambda i, n: seen.append((i, n)))
    assert seen == [(1, 2), (2, 2)]


# --- sous-titres embarqués ------------------------------------------------

def test_mux_mkv_maps_every_subtitle_track_with_its_language(ffmpeg):
    mux.mux_mkv("p.mp4", [("p.fr.srt", "fre"), ("p.en.srt", "eng")], "p.mkv")
    cmd = ffmpeg[0]
    assert cmd.count("-i") == 3                     # vidéo + 2 SRT
    assert "language=fre" in cmd and "language=eng" in cmd
    assert _arg_after(cmd, "-c:v") == "copy"        # aucun réencodage
    assert _arg_after(cmd, "-c:s") == "srt"


def test_mux_mkv_tolerates_a_video_without_audio(ffmpeg):
    # -map 0:a:0? : le "?" rend la piste audio optionnelle
    mux.mux_mkv("p.mp4", [("p.fr.srt", "fre")], "p.mkv")
    assert "0:a:0?" in ffmpeg[0]


# --- détection de plans ---------------------------------------------------

def test_scene_cuts_returns_sorted_unique_instants(monkeypatch):
    class T:
        def __init__(self, v):
            self.v = v

        def get_seconds(self):
            return self.v

    import sys
    import types
    fake = types.ModuleType("scenedetect")
    fake.ContentDetector = lambda threshold=27.0: None
    fake.detect = lambda path, det: [(T(0.0), T(10.0)), (T(10.0), T(25.0))]
    monkeypatch.setitem(sys.modules, "scenedetect", fake)
    assert scenes.scene_cuts("in.mp4") == [0.0, 10.0, 25.0]


def test_scene_cuts_degrades_to_an_empty_list_when_detection_fails():
    # Pas de vidéo -> pas de plans, mais surtout pas de crash du pipeline.
    assert scenes.scene_cuts("/does/not/exist.mp4") == []
