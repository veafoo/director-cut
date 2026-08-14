import json

import pytest

from director_cut import brands


@pytest.fixture
def workdir(tmp_path):
    """Un dossier projet avec un dossier brands/ et deux logos."""
    d = tmp_path / "brands"
    d.mkdir()
    (d / "bfm_normandie.png").write_bytes(b"png")
    (d / "tf1.png").write_bytes(b"png")
    return str(tmp_path)


def test_output_format_is_9_16():
    assert brands.OUT_W / brands.OUT_H == pytest.approx(9 / 16)


def test_available_lists_the_logos_that_are_there(workdir):
    assert brands.available(workdir) == ["bfm_normandie", "tf1"]


def test_available_on_a_project_without_brands_folder(tmp_path):
    assert brands.available(str(tmp_path)) == []


def test_load_uses_the_placement_measured_on_the_published_thumbnails(workdir):
    b = brands.load("bfm_normandie", workdir)
    assert (b.left, b.top, b.height) == (0.0759, 0.1969, 0.1151)


def test_each_channel_keeps_its_own_placement(workdir):
    bfm = brands.load("bfm_normandie", workdir)
    tf1 = brands.load("tf1", workdir)
    assert tf1.top != bfm.top       # TF1 pose son logo plus bas
    assert tf1.height < bfm.height  # et plus petit


def test_box_converts_the_placement_into_pixels(workdir):
    x, y, h = brands.load("bfm_normandie", workdir).box()
    # Valeurs relevées au pixel près sur la vignette de référence 1080x1920.
    assert (x, y, h) == (82, 378, 221)


def test_box_follows_the_output_size(workdir):
    b = brands.load("bfm_normandie", workdir)
    x, y, h = b.box(w=540, h=960)
    assert (x, y, h) == (41, 189, 110)


def test_an_unknown_channel_falls_back_on_the_default_placement(workdir):
    (pytest.importorskip("pathlib").Path(workdir) / "brands" / "x.png").write_bytes(b"png")
    b = brands.load("x", workdir)
    assert (b.left, b.top, b.height) == (
        brands.DEFAULT_PLACEMENT["left"],
        brands.DEFAULT_PLACEMENT["top"],
        brands.DEFAULT_PLACEMENT["height"])


def test_a_json_next_to_the_logo_overrides_the_placement(workdir, tmp_path):
    (tmp_path / "brands" / "tf1.json").write_text(json.dumps({"top": 0.5}))
    b = brands.load("tf1", workdir)
    assert b.top == 0.5
    assert b.left == 0.0713      # le reste du gabarit est conservé


def test_a_missing_logo_says_what_to_do(workdir):
    with pytest.raises(ValueError) as err:
        brands.load("m6", workdir)
    assert "brands/m6.png" in str(err.value)
    assert "bfm_normandie" in str(err.value)   # liste ce qui existe


def test_a_missing_logo_without_any_brand_folder(tmp_path):
    with pytest.raises(ValueError) as err:
        brands.load("m6", str(tmp_path))
    assert "vide" in str(err.value)


# --- habillage antenne ----------------------------------------------------

def test_no_furniture_is_stripped_by_default(workdir):
    b = brands.load("bfm_normandie", workdir)
    assert (b.strip_top, b.strip_bottom) == (0.0, 0.0)


def test_strip_activates_the_measured_bands(workdir):
    b = brands.load("bfm_normandie", workdir, strip=True)
    assert b.strip_top > 0 and b.strip_bottom > 0
    assert b.strip_top + b.strip_bottom < 0.5   # il reste plus de la moitié


def test_strip_on_a_channel_without_measurements_changes_nothing(workdir):
    assert brands.load("tf1", workdir, strip=True).strip_top == 0.0


# --- choix automatique ----------------------------------------------------

def test_a_single_logo_is_picked_without_asking(tmp_path):
    d = tmp_path / "brands"
    d.mkdir()
    (d / "bfm_normandie.png").write_bytes(b"png")
    assert brands.auto(None, str(tmp_path)).name == "bfm_normandie"


def test_several_logos_and_no_choice_means_no_logo(workdir):
    assert brands.auto(None, workdir) is None


def test_an_explicit_name_always_wins(workdir):
    assert brands.auto("tf1", workdir).name == "tf1"


def test_no_brands_folder_means_no_logo(tmp_path):
    assert brands.auto(None, str(tmp_path)) is None


def test_auto_passes_the_strip_flag_through(tmp_path):
    d = tmp_path / "brands"
    d.mkdir()
    (d / "bfm_normandie.png").write_bytes(b"png")
    assert brands.auto(None, str(tmp_path), strip=True).strip_top > 0
