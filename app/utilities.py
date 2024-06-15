import os

import services
from typing import Any
from fastapi import Depends, HTTPException, Query, status
from enum import IntEnum

from fastapi.security import OAuth2PasswordBearer
import jwt
from pydantic import BaseModel

from app.constants.privileges import Privileges


class Gamemode(IntEnum):
    VANILLA = 0
    RELAX = 1

    @property
    def to_db(self) -> str:
        return "stats_rx" if self == Gamemode.RELAX else "stats"


class Mode(IntEnum):
    STANDARD = 0
    TAIKO = 1
    CATCH = 2
    MANIA = 3

    def to_db(self, field: str):
        """Converts the fields name, thats depended on the mode, to match the current mode."""
        mode = ("std", "taiko", "catch", "mania")[self.value]
        return f"{field}_{mode} AS {field}"


class ModeAndGamemode:
    def __init__(self) -> None:
        self.gamemode: Gamemode = Gamemode.VANILLA
        self.mode: Mode = Mode.STANDARD

    @classmethod
    def parse(cls, mode: int = Query(0), gamemode: int = Query(0)) -> "ModeAndGamemode":
        c = cls()

        if mode < 0 or mode > 3:
            c.mode = Mode.STANDARD
        else:
            c.mode = Mode(mode)

        if gamemode < 0 or gamemode > 1:
            c.gamemode = Gamemode.VANILLA
        else:
            c.gamemode = Gamemode(gamemode)

        # incompatible pair; reset.
        if c.gamemode == Gamemode.RELAX and c.mode == Mode.MANIA:
            c.gamemode = Gamemode.VANILLA
            c.mode = Mode.STANDARD

        return c


def parse_including_query(include: list[str] = Query([])) -> list[str]:
    # parses include query field as such:
    #
    # ?include=[stats,clans] = ["stats", "clans"]
    # ?include=stats,clans = ["stats", "clans"]

    if not include:
        return []

    first_include = include[0]

    if first_include.startswith("[") and first_include.endswith("]"):
        first_include = first_include[1 : len(first_include) - 1]

    all_inc = first_include.split(",")

    return all_inc


class UserData(BaseModel):
    user_id: int
    username: str
    privileges: Privileges


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserData | None:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload: dict[str, Any] = jwt.decode(
            token, os.getenv("SECRET_KEY"), algorithms=["HS256"]
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    user_id = payload.get("sub")
    assert user_id is not None

    data = await services.database.fetch_one(
        "SELECT username, privileges FROM users WHERE id = :user_id LIMIT 1",
        {"user_id": user_id},
    )

    if not data:
        raise credentials_exception

    return UserData(
        user_id=user_id,
        username=data["username"],
        privileges=Privileges(data["privileges"]),
    )


async def log(user_id: int, note: str) -> None:
    await services.database.execute(
        "INSERT INTO logs (user_id, note) VALUES (:user_id, :note)",
        {"user_id": user_id, "note": note},
    )
