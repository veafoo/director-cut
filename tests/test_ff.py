"""Quand ffmpeg échoue, l'utilisatrice doit lire POURQUOI.

Le run réel qui a motivé ce module s'arrêtait sur « returned non-zero exit
status 254 », sans un mot sur la cause — alors que ffmpeg avait écrit
« No such file or directory » sur stderr.
"""
import subprocess

import pytest

from director_cut import ff

BANNER = """ffmpeg version 8.1.1 Copyright (c) 2000-2026 the FFmpeg developers
  built with Apple clang version 21.0.0
  configuration: --prefix=/opt/homebrew/Cellar/ffmpeg/8.1.1
  libavutil      60. 26.101 / 60. 26.101
"""


@pytest.fixture
def ffmpeg(monkeypatch):
    def _fail(code, stderr):
        def fake(cmd, capture_output=False):
            return subprocess.CompletedProcess(cmd, code, b"",
                                               stderr.encode("utf-8"))
        monkeypatch.setattr(ff.subprocess, "run", fake)
    return _fail


def test_a_successful_call_returns_the_process(monkeypatch):
    monkeypatch.setattr(ff.subprocess, "run",
                        lambda cmd, capture_output=False:
                        subprocess.CompletedProcess(cmd, 0, b"data", b""))
    assert ff.run(["ffmpeg"]).returncode == 0


def test_capture_hands_back_the_stream(monkeypatch):
    monkeypatch.setattr(ff.subprocess, "run",
                        lambda cmd, capture_output=False:
                        subprocess.CompletedProcess(cmd, 0, b"rawbytes", b""))
    assert ff.capture(["ffmpeg"]) == b"rawbytes"


def test_a_missing_input_says_so(ffmpeg):
    ffmpeg(254, BANNER + "[in#0] Error opening input: No such file or directory\n"
                         "Error opening input file sortie/raw/video.mp4.\n")
    with pytest.raises(ff.FFmpegError) as err:
        ff.run(["ffmpeg", "-i", "sortie/raw/video.mp4", "out.mp4"])
    assert "No such file or directory" in str(err.value)
    assert "sortie/raw/video.mp4" in str(err.value)


def test_the_version_banner_is_not_the_error_message(ffmpeg):
    ffmpeg(1, BANNER + "Invalid data found when processing input\n")
    with pytest.raises(ff.FFmpegError) as err:
        ff.run(["ffmpeg"])
    assert "Invalid data found" in str(err.value)
    assert "Copyright" not in str(err.value)
    assert "configuration:" not in str(err.value)


def test_the_return_code_is_kept_for_the_record(ffmpeg):
    ffmpeg(254, BANNER + "boom\n")
    with pytest.raises(ff.FFmpegError) as err:
        ff.run(["ffmpeg"])
    assert err.value.code == 254
    assert "254" in str(err.value)


def test_a_silent_failure_still_gives_something_to_read(ffmpeg):
    ffmpeg(1, "")
    with pytest.raises(ff.FFmpegError) as err:
        ff.run(["ffmpeg"])
    assert "sans message" in str(err.value)


def test_the_command_stays_available_for_debugging(ffmpeg):
    ffmpeg(1, "boom\n")
    with pytest.raises(ff.FFmpegError) as err:
        ff.run(["ffmpeg", "-i", "in.mp4"])
    assert err.value.cmd == ["ffmpeg", "-i", "in.mp4"]
    assert err.value.stderr == "boom\n"
