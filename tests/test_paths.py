from remote_job_tracker.paths import PROJECT_ROOT, data_directory


def test_data_directory_defaults_to_project_root(monkeypatch):
    monkeypatch.delenv("JOB_TRACKER_DATA_DIR", raising=False)
    assert data_directory() == PROJECT_ROOT


def test_data_directory_can_be_overridden_for_persistent_container_volume(
    monkeypatch, tmp_path
):
    target = tmp_path / "tracker-data"
    monkeypatch.setenv("JOB_TRACKER_DATA_DIR", str(target))
    assert data_directory() == target
