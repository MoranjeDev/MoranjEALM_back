"""Tests basiques de la phase 1."""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from .models import GroupeUser, Habilitation, User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_group(db):
    g = GroupeUser.objects.create(nom="Administrateurs")
    Habilitation.objects.create(
        groupe=g,
        permissions=[
            "Gestion des Utilisateurs",
            "Gestion des Groupes Utilisateurs",
            "Gestion des Habilitations",
        ],
    )
    return g


@pytest.fixture
def user_admin(db, admin_group):
    user = User.objects.create_user(
        username="admin1",
        password="StrongPassword123!",
        groupe=admin_group,
    )
    user.firstconnect = False
    user.save()
    return user


@pytest.mark.django_db
def test_health(api_client):
    resp = api_client.get("/api/health/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.django_db
def test_login_success(api_client, user_admin):
    resp = api_client.post(
        "/api/auth/login/",
        {"username": "admin1", "password": "StrongPassword123!"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access" in body and "refresh" in body
    assert body["user"]["username"] == "admin1"
    assert "Gestion des Utilisateurs" in body["user"]["habilitations"]


@pytest.mark.django_db
def test_login_invalid(api_client, user_admin):
    resp = api_client.post(
        "/api/auth/login/",
        {"username": "admin1", "password": "wrong"},
        format="json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_me_requires_auth(api_client):
    resp = api_client.get("/api/auth/me/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_change_password(api_client, user_admin):
    login = api_client.post(
        "/api/auth/login/",
        {"username": "admin1", "password": "StrongPassword123!"},
        format="json",
    ).json()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")
    resp = api_client.post(
        "/api/auth/change-password/",
        {"old_password": "StrongPassword123!", "new_password": "NewStronger987!"},
        format="json",
    )
    assert resp.status_code == 200
