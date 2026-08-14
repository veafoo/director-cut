import base64
import json
import subprocess

import pytest

from director_cut import download

PAGE_WITH_DATA_ATTRS = """
<html><body>
  <div class="video" data-account="6001234567001" data-video-id="6355123456789">
  </div>
</body></html>
"""

PAGE_WITH_M3U8 = """
<html><body>
  <video data-video-id="6355123456789"></video>
  <script>
    var src = "https://manifest.prod.boltdns.net/manifest/v1/hls/v4/clear/600/x.m3u8?bcov_auth=SIGNED";
  </script>
</body></html>
"""


def _jwt(account):
    payload = base64.urlsafe_b64encode(
        json.dumps({"accid": account}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{payload}"


PAGE_WITH_JWT = f"""
<html><body>
  <div data-video-id="6355123456789"></div>
  <script>var auth = "bcov_auth={_jwt("6009999999001")}";</script>
</body></html>
"""


@pytest.fixture
def page(monkeypatch):
    """Sert un HTML fixe à la place d'un vrai appel réseau."""
    def _serve(html):
        monkeypatch.setattr(download, "_fetch_html", lambda url: html)
    return _serve


# --- lecture de page ------------------------------------------------------

def test_brightcove_sources_builds_the_player_url_from_data_attributes(page):
    page(PAGE_WITH_DATA_ATTRS)
    sources = download._brightcove_sources("https://www.example.com/a.html")
    assert sources[0] == ("https://players.brightcove.net/6001234567001/"
                          "default_default/index.html?videoId=6355123456789")


def test_brightcove_sources_reads_the_account_from_the_bcov_auth_jwt(page):
    page(PAGE_WITH_JWT)
    sources = download._brightcove_sources("https://www.example.com/a.html")
    assert "6009999999001" in sources[0]


def test_brightcove_sources_falls_back_on_the_signed_hls_stream(page):
    page(PAGE_WITH_M3U8)
    sources = download._brightcove_sources("https://www.example.com/a.html")
    assert sources[-1].endswith(".m3u8?bcov_auth=SIGNED")


def test_brightcove_sources_returns_nothing_on_an_unrelated_page(page):
    page("<html><body>pas de vidéo ici</body></html>")
    assert download._brightcove_sources("https://www.example.com/a.html") == []


def test_brightcove_sources_survives_a_corrupt_jwt(page):
    page('<div data-video-id="123"></div><script>bcov_auth=aaa.bbb</script>')
    # Pas de compte exploitable -> pas de player, et pas d'exception.
    assert download._brightcove_sources("https://www.example.com/a.html") == []


# --- ordre des sources ----------------------------------------------------

def test_site_root_is_used_as_referer():
    assert download._site_root(
        "https://www.example.com/replay/video.html") == "https://www.example.com/"


def test_resolve_sources_reads_the_page_first_for_known_brightcove_sites(page):
    page(PAGE_WITH_DATA_ATTRS)
    host = download.BRIGHTCOVE_FIRST[0]
    url = f"https://www.{host}/replay/video.html"
    sources = download._resolve_sources(url)
    assert "players.brightcove.net" in sources[0][0]
    assert sources[0][1] == f"https://www.{host}/"
    assert sources[-1] == (url, None)   # yt-dlp reste le dernier recours


def test_resolve_sources_lets_ytdlp_lead_on_any_other_site():
    url = "https://www.youtube.com/watch?v=abc"
    assert download._resolve_sources(url) == [(url, None)]


def test_resolve_sources_leaves_a_direct_stream_untouched():
    url = "https://cdn.example.com/x.m3u8"
    assert download._resolve_sources(url) == [(url, None)]


def test_resolve_sources_leaves_a_local_path_untouched():
    assert download._resolve_sources("/tmp/video.mp4") == [("/tmp/video.mp4", None)]


# --- enchaînement des tentatives -----------------------------------------

class FakeYtdlp:
    """Remplace _run_ytdlp : échoue sur tout sauf les sources listées."""

    def __init__(self, succeeds_on=()):
        self.succeeds_on = succeeds_on
        self.calls = []

    def __call__(self, src, out_tmpl, referer=None):
        self.calls.append((src, referer))
        if not any(ok in src for ok in self.succeeds_on):
            raise subprocess.CalledProcessError(1, "yt-dlp")


@pytest.fixture
def ytdlp(monkeypatch):
    def _install(succeeds_on=()):
        fake = FakeYtdlp(succeeds_on)
        monkeypatch.setattr(download, "_run_ytdlp", fake)
        return fake
    return _install


def test_download_returns_the_file_produced_by_ytdlp(tmp_path, monkeypatch):
    def produce(src, out_tmpl, referer=None):
        (tmp_path / "video.mp4").write_bytes(b"fake")

    monkeypatch.setattr(download, "_run_ytdlp", produce)
    out = download.download("https://www.youtube.com/watch?v=abc", str(tmp_path))
    assert out.endswith("video.mp4")


def test_download_raises_when_ytdlp_produced_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "_run_ytdlp", lambda *a, **k: None)
    with pytest.raises(RuntimeError) as err:
        download.download("https://www.youtube.com/watch?v=abc", str(tmp_path))
    assert "aucune vidéo" in str(err.value)


def test_download_stops_at_the_first_source_that_works(ytdlp, tmp_path, page):
    page(PAGE_WITH_DATA_ATTRS)
    fake = ytdlp(succeeds_on=("players.brightcove.net",))
    host = download.BRIGHTCOVE_FIRST[0]
    with pytest.raises(RuntimeError):
        # aucun fichier n'est réellement produit -> l'erreur finale est normale
        download.download(f"https://www.{host}/replay/v.html", str(tmp_path))
    assert len(fake.calls) == 1
    assert "players.brightcove.net" in fake.calls[0][0]


def test_download_tries_the_page_when_ytdlp_fails_on_an_unknown_site(ytdlp,
                                                                    tmp_path,
                                                                    page):
    page(PAGE_WITH_DATA_ATTRS)
    fake = ytdlp(succeeds_on=())
    with pytest.raises(RuntimeError):
        download.download("https://www.example.com/replay/v.html", str(tmp_path))
    tried = [src for src, _ in fake.calls]
    assert tried[0] == "https://www.example.com/replay/v.html"
    assert "players.brightcove.net" in tried[1]


def test_download_error_message_points_to_the_local_file_workaround(ytdlp,
                                                                   tmp_path):
    ytdlp(succeeds_on=())
    with pytest.raises(RuntimeError) as err:
        download.download("https://cdn.example.com/x.m3u8", str(tmp_path))
    assert "director-cut run" in str(err.value)
    assert "bfm" not in str(err.value).lower()


def test_get_video_uses_a_local_file_without_downloading(tmp_path, monkeypatch):
    local = tmp_path / "reportage.mp4"
    local.write_bytes(b"fake")
    monkeypatch.setattr(download, "download", lambda *a: pytest.fail(
        "un fichier local ne doit jamais être téléchargé"))
    assert download.get_video(str(local), str(tmp_path)) == str(local)


def test_get_video_downloads_anything_that_is_not_a_local_video(tmp_path,
                                                               monkeypatch):
    monkeypatch.setattr(download, "download", lambda src, out: "downloaded")
    assert download.get_video("https://example.com/v.html", str(tmp_path)) \
        == "downloaded"
