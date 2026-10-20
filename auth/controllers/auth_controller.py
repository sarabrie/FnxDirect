from fastapi import APIRouter, Depends, HTTPException, Request, Response

from auth.middlewares.auth_middleware import (
    clear_auth_cookies,
    get_refresh_token_from_cookie,
    require_auth,
    set_auth_cookies,
    validate_csrf,
)
from auth.middlewares.rate_limiter import rate_limit
from auth.schemas import GoogleAuthRequest, LoginRequest, RegisterRequest
from auth.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", status_code=201)
def signup(body: RegisterRequest, response: Response, _rl=Depends(rate_limit)):
    try:
        access, refresh = auth_service.register(body.email, body.password, body.display_name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    set_auth_cookies(response, access, refresh)
    return {"message": "Account created."}


@router.post("/login")
def login(body: LoginRequest, response: Response, _rl=Depends(rate_limit)):
    try:
        access, refresh = auth_service.login(body.email, body.password)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    set_auth_cookies(response, access, refresh)
    return {"message": "Logged in."}


@router.post("/google")
def google_login(body: GoogleAuthRequest, response: Response):
    try:
        access, refresh = auth_service.google_auth(body.id_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    set_auth_cookies(response, access, refresh)
    return {"message": "Logged in via Google."}


@router.post("/refresh")
def refresh(request: Request, response: Response, _rl=Depends(rate_limit)):
    raw = get_refresh_token_from_cookie(request)
    if not raw:
        raise HTTPException(status_code=401, detail="No refresh token.")
    try:
        access, new_refresh = auth_service.refresh_tokens(raw)
    except ValueError as e:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail=str(e))
    set_auth_cookies(response, access, new_refresh)
    return {"message": "Tokens refreshed."}


@router.post("/logout")
def logout(request: Request, response: Response, user: dict = Depends(require_auth)):
    validate_csrf(request)
    raw = get_refresh_token_from_cookie(request)
    auth_service.logout(raw)
    clear_auth_cookies(response)
    return {"message": "Logged out."}


@router.post("/logout-all")
def logout_all(request: Request, response: Response, user: dict = Depends(require_auth)):
    validate_csrf(request)
    auth_service.logout(None, revoke_all=True, user_id=user["sub"])
    clear_auth_cookies(response)
    return {"message": "All sessions revoked."}
