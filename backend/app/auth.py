"""Pilot auth (SPEC §6): invite-code registration, username+password, signed
session cookie. Stdlib crypto only (pbkdf2 + HMAC) — no extra deps. The product
swaps this layer for real multi-league auth without touching the engine.
"""
import base64
import hashlib
import hmac
import os
import time

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import User

COOKIE = "gridx_session"
SESSION_DAYS = 30
_ITERATIONS = 300_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def _sign(payload: str) -> str:
    return hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session_token(user_id: int) -> str:
    payload = f"{user_id}.{int(time.time()) + SESSION_DAYS * 86400}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{encoded}.{_sign(payload)}"


def read_session_token(token: str) -> int | None:
    try:
        encoded, sig = token.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(encoded.encode()).decode()
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        user_id, expires = payload.split(".")
        if int(expires) < time.time():
            return None
        return int(user_id)
    except (ValueError, TypeError):
        return None


def set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        COOKIE,
        make_session_token(user_id),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE)


def get_session():
    with SessionLocal() as session:
        yield session


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE)
    user_id = read_session_token(token) if token else None
    user = session.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return user


def current_commissioner(user: User = Depends(current_user)) -> User:
    if not user.is_commissioner:
        raise HTTPException(status_code=403, detail="commissioner only")
    return user
