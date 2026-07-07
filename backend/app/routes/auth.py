from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import (
    clear_session_cookie,
    current_user,
    get_session,
    hash_password,
    set_session_cookie,
    verify_password,
)
from app.models import League, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    invite_code: str
    username: str = Field(min_length=2, max_length=24, pattern=r"^[a-zA-Z0-9_ ]+$")
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str
    password: str


def _me(user: User, session: Session) -> dict:
    league = session.get(League, user.league_id)
    return {
        "user_id": user.id,
        "username": user.username,
        "is_commissioner": user.is_commissioner,
        "league": {"id": league.id, "name": league.name, "season": league.season_year},
        "cash": float(user.cash),
    }


@router.post("/register")
def register(body: RegisterIn, response: Response, session: Session = Depends(get_session)):
    league = session.execute(
        select(League).where(League.invite_code == body.invite_code)
    ).scalar_one_or_none()
    if league is None:
        raise HTTPException(status_code=400, detail="invalid invite code")
    username = body.username.strip()
    # names are matched case-insensitively (a phone auto-capitalizes) — so "Ryan"
    # and "ryan" are the same account and can't both be registered.
    taken = session.execute(
        select(User).where(
            User.league_id == league.id, func.lower(User.username) == username.lower()
        )
    ).scalar_one_or_none()
    if taken:
        raise HTTPException(status_code=400, detail="that name is taken in this league")
    member_count = session.execute(
        select(func.count()).select_from(User).where(User.league_id == league.id)
    ).scalar()
    user = User(
        league_id=league.id,
        username=username,
        pw_hash=hash_password(body.password),
        cash=league.rules.starting_cash,
        # first member in bootstraps as commissioner
        is_commissioner=(member_count == 0),
    )
    session.add(user)
    session.commit()
    set_session_cookie(response, user.id)
    return _me(user, session)


@router.post("/login")
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)):
    # case-insensitive name match — the password stays exact
    user = session.execute(
        select(User).where(func.lower(User.username) == body.username.strip().lower())
    ).scalars().first()
    if user is None or not user.pw_hash or not verify_password(body.password, user.pw_hash):
        raise HTTPException(status_code=401, detail="wrong name or password")
    set_session_cookie(response, user.id)
    return _me(user, session)


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _me(user, session)
