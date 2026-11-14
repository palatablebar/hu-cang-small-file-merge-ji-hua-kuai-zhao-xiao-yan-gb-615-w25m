"""权限依赖单测：401 / 403 / 放行，以及三角色权限矩阵。"""
from __future__ import annotations

import pytest
from starlette.requests import Request

from src.constants.roles import (
    AUDIT_ROLES,
    EXPORT_ROLES,
    PLAN_CREATE_ROLES,
    PLAN_EXECUTE_ROLES,
    PLAN_REVIEW_ROLES,
    READ_ROLES,
    SNAPSHOT_VERIFY_ROLES,
    TABLE_WRITE_ROLES,
    has_permission,
)
from src.middlewares.rbac import principal_of, require_roles
from src.utils.errors import AppError


def _request(principal: dict | None = None) -> Request:
    scope = {"type": "http", "method": "GET", "path": "/api/tables", "headers": [], "state": {}}
    request = Request(scope)
    request.state.principal = principal
    return request


def test_missing_token_maps_to_401():
    with pytest.raises(AppError) as excinfo:
        principal_of(_request(None))
    assert excinfo.value.code == "AUTH_MISSING"
    assert excinfo.value.status_code == 401


def test_viewer_write_is_403():
    dependency = require_roles(*TABLE_WRITE_ROLES)
    with pytest.raises(AppError) as excinfo:
        dependency(_request({"email": "viewer@compactlab.io", "role": "viewer"}))
    assert excinfo.value.code == "FORBIDDEN"
    assert excinfo.value.status_code == 403


def test_analyst_can_review_but_cannot_create_or_execute():
    review = require_roles(*PLAN_REVIEW_ROLES)
    assert review(_request({"email": "analyst@compactlab.io", "role": "analyst"}))["role"] == "analyst"

    for roles in (PLAN_CREATE_ROLES, PLAN_EXECUTE_ROLES, EXPORT_ROLES, AUDIT_ROLES):
        dependency = require_roles(*roles)
        with pytest.raises(AppError) as excinfo:
            dependency(_request({"email": "analyst@compactlab.io", "role": "analyst"}))
        assert excinfo.value.status_code == 403


def test_admin_and_readers():
    read = require_roles(*READ_ROLES)
    for role in ("admin", "analyst", "viewer"):
        assert read(_request({"email": f"{role}@compactlab.io", "role": role}))["role"] == role

    execute = require_roles(*PLAN_EXECUTE_ROLES)
    assert execute(_request({"email": "admin@compactlab.io", "role": "admin"}))["role"] == "admin"

    with pytest.raises(AppError) as excinfo:
        require_roles(*SNAPSHOT_VERIFY_ROLES)(_request({"email": "viewer@compactlab.io", "role": "viewer"}))
    assert excinfo.value.status_code == 403


def test_permission_matrix_matches_roles():
    assert has_permission("admin", "plan:execute") is True
    assert has_permission("analyst", "plan:review") is True
    assert has_permission("analyst", "export:read") is False
    assert has_permission("viewer", "plan:read") is True
    assert has_permission("viewer", "plan:create") is False
    assert has_permission("viewer", "audit:read") is False
