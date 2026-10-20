from fastapi import APIRouter, Depends, HTTPException, Request

from auth.middlewares.auth_middleware import optional_auth, require_auth, validate_csrf
from auth.schemas import GuestMigrateRequest, HistoryPage, PreferencesUpdate
from auth.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def get_profile(user: dict = Depends(require_auth)):
    try:
        return user_service.get_profile(user["sub"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/me/greeting")
def greeting(user: dict | None = Depends(optional_auth)):
    if user is None:
        return {"greeting": "Welcome, Guest!", "authenticated": False}
    return {"greeting": f"Welcome back, {user['name']}!", "authenticated": True}


@router.patch("/me/preferences")
def update_preferences(
    request: Request,
    body: PreferencesUpdate,
    user: dict = Depends(require_auth),
):
    validate_csrf(request)
    result = user_service.update_preferences(user["sub"], body.theme, body.settings_json)
    return {"theme": result["theme"], "settings_json": result["settings_json"]}


@router.get("/me/history")
def get_history(
    limit: int = 20,
    before_id: str | None = None,
    user: dict = Depends(require_auth),
):
    page = HistoryPage(limit=limit, before_id=before_id)
    return user_service.get_history(user["sub"], page.limit, page.before_id)


@router.post("/me/migrate-guest", status_code=200)
def migrate_guest(
    request: Request,
    body: GuestMigrateRequest,
    user: dict = Depends(require_auth),
):
    validate_csrf(request)
    count = user_service.migrate_guest_data(user["sub"], body.guest_actions)
    return {"migrated": count}
