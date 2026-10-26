"""Session cookie auth. Argon2id passwords. Optional TOTP."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from passlib.hash import argon2

from .database import get_db
from .models import AuthSession, Household, User

COOKIE_NAME = "session"
SESSION_DAYS = 14
AUTH_DISABLED = os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")

router = APIRouter()


class LoginIn(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None


class TotpConfirmIn(BaseModel):
    code: str


class TotpDisableIn(BaseModel):
    code: str
    password: str


def hash_password(password: str) -> str:
    return argon2.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return argon2.verify(password, password_hash)


def _secure_cookie(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(request),
        path="/",
        max_age=SESSION_DAYS * 86400,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def bootstrap(db: Session) -> None:
    if db.query(User).count() > 0:
        return
    username = os.getenv("BOOTSTRAP_USERNAME")
    password = os.getenv("BOOTSTRAP_PASSWORD")
    if not username or not password:
        return
    household = Household(name=os.getenv("HOUSEHOLD_NAME", "Household"))
    db.add(household)
    db.flush()
    db.add(
        User(
            household_id=household.id,
            username=username,
            password_hash=hash_password(password),
        )
    )
    db.commit()


def create_session(db: Session, user: User, profile_id: Optional[int] = None) -> AuthSession:
    sess = AuthSession(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        active_profile_id=profile_id,
        expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def load_session(db: Session, token: Optional[str]) -> Optional[AuthSession]:
    if not token:
        return None
    sess = db.query(AuthSession).filter(AuthSession.token == token).first()
    if not sess:
        return None
    if sess.expires_at and sess.expires_at < datetime.utcnow():
        return None
    return sess


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    if AUTH_DISABLED:
        user = db.query(User).first()
        if user:
            request.state.user = user
            request.state.auth_session = None
            return user
        raise HTTPException(401, "login required")
    sess = load_session(db, request.cookies.get(COOKIE_NAME))
    if not sess or not sess.user:
        raise HTTPException(401, "login required")
    request.state.user = sess.user
    request.state.auth_session = sess
    return sess.user


def household_id_for(request: Request, db: Session) -> int:
    user = getattr(request.state, "user", None)
    if user is not None:
        return int(user.household_id)
    if AUTH_DISABLED:
        return 1
    token = request.cookies.get(COOKIE_NAME)
    sess = load_session(db, token)
    if sess and sess.user:
        return int(sess.user.household_id)
    return 1


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    if user.totp_enabled:
        if not body.totp_code:
            raise HTTPException(401, "totp_required")
        if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(body.totp_code, valid_window=1):
            raise HTTPException(401, "invalid totp")
    sess = create_session(db, user)
    set_session_cookie(response, request, sess.token)
    return {
        "ok": True,
        "username": user.username,
        "active_profile_id": sess.active_profile_id,
        "totp_enabled": bool(user.totp_enabled),
    }


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.query(AuthSession).filter(AuthSession.token == token).delete()
        db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sess = getattr(request.state, "auth_session", None)
    return {
        "id": user.id,
        "username": user.username,
        "household_id": user.household_id,
        "totp_enabled": bool(user.totp_enabled),
        "active_profile_id": sess.active_profile_id if sess else None,
    }


@router.post("/session/active-profile/{profile_id}")
def set_active_profile(
    profile_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from .models import Profile

    profile = (
        db.query(Profile)
        .filter(Profile.id == profile_id, Profile.household_id == user.household_id)
        .first()
    )
    if not profile:
        raise HTTPException(404, "profile not found")
    sess = getattr(request.state, "auth_session", None)
    if sess:
        sess.active_profile_id = profile.id
        db.commit()
    return {"active_profile_id": profile.id}


@router.post("/totp/start")
def totp_start(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    secret = pyotp.random_base32()
    user.totp_secret = secret
    user.totp_enabled = False
    db.commit()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.username, issuer_name="Household PHR")
    return {"secret": secret, "otpauth_url": uri}


@router.post("/totp/confirm")
def totp_confirm(body: TotpConfirmIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not user.totp_secret:
        raise HTTPException(400, "enroll first")
    if not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(400, "invalid totp")
    user.totp_enabled = True
    db.commit()
    return {"totp_enabled": True}


@router.post("/totp/disable")
def totp_disable(body: TotpDisableIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    if user.totp_enabled:
        if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
            raise HTTPException(401, "invalid totp")
    user.totp_enabled = False
    user.totp_secret = None
    db.commit()
    return {"totp_enabled": False}
