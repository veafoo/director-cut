"""Un seul run à la fois par dossier de sortie.

Deux runs simultanés partagent raw/video.mp4 : le second retélécharge par-dessus
et le premier voit sa source disparaître en plein travail.
"""
import os

import pytest

from director_cut import lock


def test_a_free_folder_can_be_taken(tmp_path):
    with lock.Lock(str(tmp_path)):
        assert os.path.exists(tmp_path / lock.LOCK_NAME)


def test_the_lock_is_released_at_the_end(tmp_path):
    with lock.Lock(str(tmp_path)):
        pass
    assert not os.path.exists(tmp_path / lock.LOCK_NAME)


def test_the_lock_is_released_even_when_the_run_fails(tmp_path):
    with pytest.raises(ValueError):
        with lock.Lock(str(tmp_path)):
            raise ValueError("le run a planté")
    assert not os.path.exists(tmp_path / lock.LOCK_NAME)


def test_a_second_run_on_the_same_folder_is_refused(tmp_path, monkeypatch):
    # Un autre processus, bien vivant, tient le verrou.
    (tmp_path / lock.LOCK_NAME).write_text("999999")
    monkeypatch.setattr(lock, "_alive", lambda pid: True)
    with pytest.raises(lock.Busy) as err:
        with lock.Lock(str(tmp_path)):
            pass
    assert "999999" in str(err.value)
    assert "--out" in str(err.value)      # dit quoi faire


def test_the_refusal_does_not_destroy_the_other_run_lock(tmp_path, monkeypatch):
    (tmp_path / lock.LOCK_NAME).write_text("999999")
    monkeypatch.setattr(lock, "_alive", lambda pid: True)
    with pytest.raises(lock.Busy):
        with lock.Lock(str(tmp_path)):
            pass
    assert (tmp_path / lock.LOCK_NAME).read_text() == "999999"


def test_a_lock_left_by_a_dead_run_is_reclaimed(tmp_path, monkeypatch):
    # Sinon un plantage bloquerait le dossier pour toujours.
    (tmp_path / lock.LOCK_NAME).write_text("999999")
    monkeypatch.setattr(lock, "_alive", lambda pid: False)
    with lock.Lock(str(tmp_path)):
        assert (tmp_path / lock.LOCK_NAME).read_text() == str(os.getpid())


def test_a_corrupt_lock_file_is_reclaimed(tmp_path):
    (tmp_path / lock.LOCK_NAME).write_text("n'importe quoi")
    with lock.Lock(str(tmp_path)):
        assert (tmp_path / lock.LOCK_NAME).read_text() == str(os.getpid())


def test_our_own_pid_never_blocks_us(tmp_path):
    (tmp_path / lock.LOCK_NAME).write_text(str(os.getpid()))
    with lock.Lock(str(tmp_path)):
        pass


def test_a_dead_pid_is_seen_as_dead():
    # PID 999999 n'existe pas sur une machine normale.
    assert lock._alive(os.getpid()) is True
    assert lock._alive(999999) is False
