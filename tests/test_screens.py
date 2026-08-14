"""Vignettes 9:16 : géométrie du rendu et choix de l'instant le plus net."""
import subprocess

import numpy as np
import pytest

from director_cut import brands, screens


@pytest.fixture
def brand(tmp_path):
    d = tmp_path / "brands"
    d.mkdir()
    (d / "bfm_normandie.png").write_bytes(b"png")
    return brands.load("bfm_normandie", str(tmp_path))


@pytest.fixture
def ffmpeg(monkeypatch):
    calls = []
    monkeypatch.setattr(screens, "_run", calls.append)
    return calls


def _arg_after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


# --- chaîne de filtres ----------------------------------------------------

def test_the_image_fills_the_whole_thumbnail():
    chain = screens.vertical_chain()
    assert "crop='min(iw,ih*1080/1920)':'min(ih,iw*1920/1080)'" in chain
    assert "scale=1080:1920" in chain


def test_no_more_blurred_background():
    # C'était le rendu d'avant : petite image flottant dans un fond flou.
    chain = screens.vertical_chain()
    assert "boxblur" not in chain
    assert "force_original_aspect_ratio" not in chain


def test_the_upscale_uses_lanczos():
    assert "flags=lanczos" in screens.vertical_chain()


def test_a_sharpening_pass_compensates_the_upscale():
    assert "unsharp=5:5:0.8:5:5:0.0" in screens.vertical_chain(sharpen=0.8)


def test_sharpening_can_be_switched_off():
    assert "unsharp" not in screens.vertical_chain(sharpen=0)


def test_stripping_the_furniture_crops_the_source_first():
    chain = screens.vertical_chain(strip_top=0.139, strip_bottom=0.243)
    assert chain.startswith("crop=iw:ih*0.6180:0:ih*0.1390,")


def test_without_stripping_the_source_is_not_pre_cropped():
    assert not screens.vertical_chain().startswith("crop=iw:")


# --- commande de rendu ----------------------------------------------------

def test_the_logo_lands_exactly_where_the_template_puts_it(brand, ffmpeg):
    screens.grab_vertical("in.mp4", 12.0, "out.jpg", brand=brand)
    fc = _arg_after(ffmpeg[0], "-filter_complex")
    assert "overlay=82:378" in fc
    assert "scale=-1:221" in fc      # hauteur du logo du gabarit


def test_the_logo_is_a_second_input(brand, ffmpeg):
    screens.grab_vertical("in.mp4", 12.0, "out.jpg", brand=brand)
    assert ffmpeg[0].count("-i") == 2
    assert brand.logo in ffmpeg[0]


def test_without_a_brand_there_is_no_overlay(ffmpeg):
    screens.grab_vertical("in.mp4", 12.0, "out.jpg", brand=None)
    cmd = ffmpeg[0]
    assert "-filter_complex" not in cmd
    assert "crop=" in _arg_after(cmd, "-vf")


def test_the_capture_seeks_to_the_requested_instant(brand, ffmpeg):
    screens.grab_vertical("in.mp4", 12.5, "out.jpg", brand=brand)
    assert _arg_after(ffmpeg[0], "-ss") == "12.500"


def test_the_frame_is_taken_from_the_video_in_a_single_pass(brand, ffmpeg):
    # Pas de capture intermédiaire : on recadre sur la source pleine définition.
    screens.grab_vertical("in.mp4", 12.0, "out.jpg", brand=brand)
    assert ffmpeg[0][ffmpeg[0].index("-i") + 1] == "in.mp4"
    assert len(ffmpeg) == 1


def test_converting_an_existing_image_does_not_seek(brand, ffmpeg):
    screens.to_vertical("shot.png", "out.jpg", brand=brand)
    assert "-ss" not in ffmpeg[0]


# --- netteté --------------------------------------------------------------

def test_sharpness_ranks_a_crisp_image_above_a_blurred_one():
    rng = np.random.default_rng(0)
    crisp = rng.integers(0, 255, (64, 64)).astype(np.uint8)
    # moyenne glissante = version floue de la même image
    blurred = crisp.astype(float)
    for _ in range(3):
        blurred = (blurred + np.roll(blurred, 1, 0) + np.roll(blurred, 1, 1)) / 3
    assert screens.sharpness(crisp) > screens.sharpness(blurred)


def test_sharpness_of_a_flat_image_is_zero():
    assert screens.sharpness(np.full((32, 32), 128, np.uint8)) == 0.0


def test_best_time_picks_the_least_blurred_candidate(monkeypatch):
    seen = []

    def fake_gray(video, t, size=192):
        seen.append(round(t, 3))
        # la frame à 10.3 est la nette, les autres sont plates
        return (np.arange(size * size).reshape(size, size) % 255).astype(np.uint8) \
            if abs(t - 10.3) < 1e-6 else np.zeros((size, size), np.uint8)

    monkeypatch.setattr(screens, "_gray_frame", fake_gray)
    best = screens.best_time("in.mp4", 10.0, window=0.6, candidates=5)
    assert best == pytest.approx(10.3)
    assert len(seen) == 5


def test_best_time_never_seeks_before_the_start_of_the_video(monkeypatch):
    seen = []
    monkeypatch.setattr(screens, "_gray_frame",
                        lambda v, t, size=192: seen.append(t) or
                        np.zeros((size, size), np.uint8))
    screens.best_time("in.mp4", 0.1, window=1.0, candidates=5)
    assert min(seen) >= 0.0


def test_best_time_falls_back_on_the_requested_instant(monkeypatch):
    monkeypatch.setattr(screens, "_gray_frame", lambda v, t, size=192: None)
    assert screens.best_time("in.mp4", 42.0) == 42.0


def test_best_time_survives_a_frame_ffmpeg_cannot_decode(monkeypatch):
    def boom(video, t, size=192):
        raise subprocess.CalledProcessError(1, "ffmpeg")

    monkeypatch.setattr(screens, "_gray_frame", boom)
    assert screens.best_time("in.mp4", 42.0) == 42.0


def test_a_single_candidate_means_no_search(monkeypatch):
    monkeypatch.setattr(screens, "_gray_frame",
                        lambda *a, **k: pytest.fail("aucune recherche attendue"))
    assert screens.best_time("in.mp4", 42.0, candidates=1) == 42.0


# --- répartition des vignettes -------------------------------------------

@pytest.fixture
def no_search(monkeypatch):
    """Neutralise le choix de l'instant pour tester la seule répartition."""
    monkeypatch.setattr(screens, "best_time",
                        lambda video, t, window=0, candidates=0: t)


def test_shots_spreads_the_captures_inside_the_passage(no_search, ffmpeg,
                                                       tmp_path):
    screens.shots("in.mp4", 0.0, 100.0, str(tmp_path), "passage_01", n=4)
    assert [_arg_after(c, "-ss") for c in ffmpeg] == ["20.000", "40.000",
                                                      "60.000", "80.000"]


def test_shots_returns_one_jpg_per_capture(no_search, ffmpeg, tmp_path):
    out = screens.shots("in.mp4", 0.0, 10.0, str(tmp_path), "passage_01", n=3)
    assert [o.split("/")[-1] for o in out] == ["passage_01_01.jpg",
                                               "passage_01_02.jpg",
                                               "passage_01_03.jpg"]


def test_shots_survives_a_zero_length_passage(no_search, ffmpeg, tmp_path):
    assert len(screens.shots("in.mp4", 5.0, 5.0, str(tmp_path), "p", n=2)) == 2


def test_shots_passes_the_brand_to_every_capture(no_search, ffmpeg, tmp_path,
                                                 brand):
    screens.shots("in.mp4", 0.0, 60.0, str(tmp_path), "p", n=3, brand=brand)
    assert all("overlay=82:378" in _arg_after(c, "-filter_complex")
               for c in ffmpeg)


def test_the_search_window_never_overlaps_the_next_thumbnail(monkeypatch,
                                                             ffmpeg, tmp_path):
    windows = []
    monkeypatch.setattr(screens, "best_time",
                        lambda video, t, window, candidates: windows.append(window) or t)
    # 4 vignettes dans 3 s : les instants visés sont espacés de 0.6 s
    screens.shots("in.mp4", 0.0, 3.0, str(tmp_path), "p", n=4)
    assert max(windows) <= 3.0 / 6
