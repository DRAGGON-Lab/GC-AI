"""Detector readiness and concurrent cold-start regressions without Torch/MySQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app import config, create_app
from app.routes import component_routes, healthcheck_routes
from app.utils.custom_error import CustomError
from gcai import GCAIClient


@pytest.fixture
def readiness(monkeypatch):
    detector = object()
    loader = Mock(return_value=detector)
    monkeypatch.setattr(config, "model", None)
    monkeypatch.setattr(config, "load_model", loader)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchall.return_value = [("BBa_R0010",)]
    cursor.fetchone.return_value = (1,)
    connection = SimpleNamespace(cursor=lambda: cursor, close=Mock())
    database = Mock(return_value=connection)
    monkeypatch.setattr(component_routes, "get_db_connection", database)
    monkeypatch.setattr(healthcheck_routes, "get_db_connection", database)
    app = create_app({"TESTING": True})
    return app, loader, database, detector


def test_factory_does_not_load_detector(readiness):
    _, loader, database, _ = readiness
    loader.assert_not_called()
    database.assert_not_called()


def test_cold_and_warm_names_load_once_before_database(readiness):
    app, loader, database, detector = readiness
    database.side_effect = lambda: (
        pytest.fail("Database queried before detector readiness")
        if config.model is not detector
        else database.return_value
    )
    for _ in range(2):
        response = app.test_client().get("/component/names?role=Promoter")
        assert response.status_code == 200
        assert response.json == ["BBa_R0010"]
    loader.assert_called_once_with()
    assert database.call_count == 2


@pytest.mark.parametrize(
    "failure", [CustomError("/private/checkpoint missing", 500), None]
)
def test_unavailable_detector_is_not_healthy_and_does_not_open_database(
    readiness, failure
):
    app, loader, database, _ = readiness
    if failure is None:
        loader.return_value = None
    else:
        loader.side_effect = failure
    response = app.test_client().get("/component/names?role=Promoter")
    assert response.status_code == 500
    assert response.json["code"] == "internal_error"
    assert b"/private/" not in response.data
    with GCAIClient(
        "http://gcai.test", transport=httpx.WSGITransport(app=app)
    ) as client:
        assert client.health() is False
    database.assert_not_called()
    assert config.model is None


@pytest.mark.parametrize("query", ["", "?role=invalid"])
def test_invalid_role_does_not_initialize_detector(readiness, query):
    app, loader, database, _ = readiness
    assert app.test_client().get("/component/names" + query).status_code == 400
    loader.assert_not_called()
    database.assert_not_called()


def test_database_failure_is_not_healthy(readiness):
    app, loader, database, _ = readiness
    database.side_effect = RuntimeError("database unavailable")
    with GCAIClient(
        "http://gcai.test", transport=httpx.WSGITransport(app=app)
    ) as client:
        assert client.health() is False
    loader.assert_called_once_with()


def test_concurrent_cold_callers_share_one_detector(readiness, monkeypatch):
    _, _, _, detector = readiness
    start = Barrier(5)
    loading = Event()
    release = Event()
    duplicate = Event()
    counter_lock = Lock()
    calls = []

    def load():
        with counter_lock:
            calls.append(1)
            if len(calls) > 1:
                duplicate.set()
        loading.set()
        assert release.wait(5), "Loader was not released"
        return detector

    def get():
        start.wait(timeout=5)
        return config.get_model()

    monkeypatch.setattr(config, "load_model", load)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(get) for _ in range(4)]
        try:
            start.wait(timeout=5)
            assert loading.wait(5)
            # Hold the first load while other synchronized callers enter.
            assert not duplicate.wait(
                0.2
            ), "Concurrent callers loaded duplicate detectors"
        finally:
            release.set()
        assert all(f.result(timeout=5) is detector for f in futures)
    assert len(calls) == 1


def test_failed_initialization_can_retry(readiness):
    _, loader, _, detector = readiness
    loader.side_effect = [CustomError("checkpoint unavailable", 500), detector]
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(CustomError):
            pool.submit(config.get_model).result(timeout=5)
        assert config.model is None
        assert pool.submit(config.get_model).result(timeout=5) is detector
    assert loader.call_count == 2


class StrictCursor:
    def __init__(self, failure=None):
        self.unread = False
        self.closed = False
        self.failure = failure

    def execute(self, query):
        assert query == "SELECT 1"
        if self.failure == "execute":
            raise RuntimeError("private query failure")
        self.unread = True

    def fetchone(self):
        if self.failure == "fetch":
            raise RuntimeError("private fetch failure")
        self.unread = False
        return (1,) if self.failure != "result" else (0,)

    def close(self):
        self.closed = True
        if self.unread:
            raise RuntimeError("Unread result found")


def test_readiness_consumes_result_and_sdk_uses_readiness(readiness, monkeypatch):
    app, _, database, _ = readiness
    cursor = StrictCursor()
    connection = SimpleNamespace(cursor=lambda: cursor, close=Mock())
    database.return_value = connection
    response = app.test_client().get("/healthcheck/")
    assert response.status_code == 200, response.json
    assert response.json == {
        "status": "healthy",
        "message": "Application is running correctly",
    }
    assert cursor.closed and not cursor.unread
    connection.close.assert_called_once()
    with GCAIClient(
        "http://gcai.test", transport=httpx.WSGITransport(app=app)
    ) as client:
        assert client.health() is True


@pytest.mark.parametrize("failure", ["execute", "fetch", "result", "cursor", "connect"])
def test_readiness_failure_closes_resources_and_is_sanitized(readiness, failure):
    app, _, database, _ = readiness
    cursor = StrictCursor(failure)
    connection = SimpleNamespace(cursor=Mock(return_value=cursor), close=Mock())
    database.return_value = connection
    if failure == "cursor":
        connection.cursor.side_effect = RuntimeError("private cursor failure")
    if failure == "connect":
        database.side_effect = RuntimeError("password=private")
    response = app.test_client().get("/healthcheck/")
    assert response.status_code == 503
    assert response.json["code"] == "not_ready"
    assert b"private" not in response.data
    if failure != "connect":
        connection.close.assert_called_once()
    if failure not in {"connect", "cursor"}:
        assert cursor.closed


def test_liveness_does_not_touch_dependencies(readiness):
    app, loader, database, _ = readiness
    loader.side_effect = RuntimeError("unavailable")
    database.side_effect = RuntimeError("unavailable")
    response = app.test_client().get("/livez")
    assert response.status_code == 200
    assert response.json["status"] == "alive"
    loader.assert_not_called()
    database.assert_not_called()
