import hashlib
import os
import bcrypt
import jwt
import services

from fastapi import Form
from datetime import datetime, timedelta

from fastapi.responses import ORJSONResponse
from app.api import router

from app.constants.privileges import Privileges


@router.post("/auth/token")
async def create_token(
    username: str = Form(),
    password: bytes = Form(),
) -> ORJSONResponse:
    safe_username = username.lower().replace(" ", "_")
    user = await services.database.fetch_one(
        "SELECT id, username, passhash, privileges  FROM users WHERE safe_username = :safe_username",
        {"safe_username": safe_username},
    )

    if not user:
        return ORJSONResponse(
            {"error": "You have entered an incorrect username or password."},
            status_code=401,
        )

    if not bcrypt.checkpw(password, user["passhash"].encode()):
        return ORJSONResponse(
            {"error": "You have entered an incorrect username or password."},
            status_code=401,
        )

    ctx = {
        "username": user["username"],
        "privileges": user["privileges"],
        "is_bat": bool(user["privileges"] & Privileges.BAT),
        "is_staff": bool(
            user["privileges"] & Privileges.BAT
            | Privileges.MODERATOR
            | Privileges.ADMIN
            | Privileges.DEV
        ),
        "is_admin": bool(user["privileges"] & Privileges.ADMIN),
    }

    now = datetime.now()
    exp = now + timedelta(days=14)
    token = jwt.encode(
        {"sub": user["id"], "iat": now, "exp": exp, "context": ctx},
        key=os.getenv("SECRET_KEY"),
    )

    return ORJSONResponse(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": exp,
        },
        headers={"Cache-Control": "no-store"},
    )
