from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import engine
from app.main import app
from app.models import Base


@pytest.fixture(autouse=True)
def clean_database():
    import asyncio

    async def reset():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(reset())
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(client, email='admin@example.com', password='admin-password-for-tests'):
    response = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def test_health(client):
    assert client.get('/api/health').json() == {'status': 'ok'}


def test_missing_token_is_unauthorized(client):
    response = client.get('/api/auth/me')
    assert response.status_code == 401
    assert response.headers['www-authenticate'] == 'Bearer'


def test_register_login_and_role_protection(client):
    created = client.post('/api/auth/register', json={'email': 'viewer@example.com', 'password': 'viewer-password'})
    assert created.status_code == 201
    headers = login(client, 'viewer@example.com', 'viewer-password')
    denied = client.post('/api/records', headers=headers, json={'title': 'x', 'value': 1, 'category': 'test'})
    assert denied.status_code == 403


def test_record_crud_and_analytics(client):
    headers = login(client)
    created = client.post('/api/records', headers=headers, json={'title': 'Temperature', 'value': 82.5, 'category': 'temperature'})
    assert created.status_code == 201
    record_id = created.json()['id']
    assert client.patch(f'/api/records/{record_id}', headers=headers, json={'value': 85}).json()['value'] == 85
    summary = client.get('/api/analytics/summary', headers=headers).json()
    assert summary['count'] == 1
    assert summary['average'] == 85
    assert client.delete(f'/api/records/{record_id}', headers=headers).status_code == 204
