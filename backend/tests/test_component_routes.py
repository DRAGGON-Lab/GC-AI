"""Registry route coverage uses a query-recording fake; no server or weights."""
from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from app import create_app
from app.routes import component_routes


@pytest.fixture
def registry(monkeypatch):
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    connection = SimpleNamespace(cursor=lambda: cursor, close=Mock())
    monkeypatch.setattr(component_routes, "get_db_connection", lambda: connection)
    monkeypatch.setattr(component_routes, "get_model", Mock(return_value=object()))
    return create_app({"TESTING": True}).test_client(), cursor, connection


@pytest.mark.parametrize("query", ["", "?role=unknown"])
def test_names_invalid_role_never_initializes_dependencies(registry, query):
    client, cursor, connection = registry
    assert client.get('/component/names' + query).status_code == 400
    cursor.execute.assert_not_called()
    component_routes.get_model.assert_not_called()
    connection.close.assert_not_called()


def test_names_query_uses_bound_values_and_closes_connection(registry):
    client, cursor, connection = registry
    cursor.fetchall.return_value = [('BBa_X',), ('BBa_Y',)]
    response = client.get('/component/names?role=CDS')
    assert response.status_code == 200
    assert response.json == ['BBa_X', 'BBa_Y']
    sql, values = cursor.execute.call_args.args
    assert 'part_type IN (%s' in sql and 'coding' in values
    connection.close.assert_called_once()


@pytest.mark.parametrize("row,status", [(None, 404), (('description', 'acgt', 4), 200)])
def test_details_bind_input_and_preserve_missing_status(registry, row, status):
    client, cursor, connection = registry
    cursor.fetchone.return_value = row
    name = "a' OR 1=1 --"
    response = client.get('/component/details', query_string={'component_name': name, 'role': 'CDS'})
    assert response.status_code == status
    sql, values = cursor.execute.call_args.args
    assert name not in sql and values == (name,)
    connection.close.assert_called_once()
    if status == 200:
        assert response.json['sequence'] == 'acgt'
        assert response.json['role'] == 'CDS'


def test_details_dependency_failure_is_sanitized_and_closes(registry):
    client, cursor, connection = registry
    cursor.execute.side_effect = RuntimeError('private-password')
    response = client.get('/component/details?component_name=BBa_X')
    assert response.status_code == 500
    assert b'private-password' not in response.data
    connection.close.assert_called_once()
