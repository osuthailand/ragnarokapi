from hashlib import md5
import os
from pathlib import Path
import struct

import services
from typing import Any
from fastapi import HTTPException, Header, Query
from enum import IntEnum

import jwt
from pydantic import BaseModel

from app.constants.privileges import Privileges


class Gamemode(IntEnum):
    VANILLA = 0
    RELAX = 1

    @property
    def to_db(self) -> str:
        return "stats_rx" if self == Gamemode.RELAX else "stats"

    @property
    def score_order(self) -> str:
        return "pp" if self == Gamemode.RELAX else "score"


class Mode(IntEnum):
    STANDARD = 0
    TAIKO = 1
    CATCH = 2
    MANIA = 3

    def to_db(self, field: str, with_alias: bool = True):
        """Converts the fields name, thats depended on the mode, to match the current mode."""
        mode = ("std", "taiko", "catch", "mania")[self.value]
        return f"{field}_{mode}" + (f" AS {field}" if with_alias else "")


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


async def get_current_user(authorization: str | None = Header(None)) -> UserData | None:
    if not authorization:
        return

    type, token = authorization.split()

    if type.lower() != "bearer":
        return

    try:
        payload: dict[str, Any] = jwt.decode(
            token, os.getenv("SECRET_KEY"), algorithms=["HS256"]
        )
    except jwt.InvalidTokenError:
        raise HTTPException(401, {"error": "could not validate jwt token"})

    user_id = payload.get("sub")
    assert user_id is not None

    data = await services.database.fetch_one(
        "SELECT username, privileges FROM users WHERE id = :user_id LIMIT 1",
        {"user_id": user_id},
    )

    if not data:
        raise HTTPException(401, {"error": "could not validate jwt token"})

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


async def write_replay(score_id: int) -> bytearray | None:
    RAGNAROK_REPLAYS_PATH = Path(os.environ["RAGNAROK_REPLAYS_PATH"])

    def write_uleb128(value: int) -> bytearray:
        if value == 0:
            return bytearray(b"\x00")

        data: bytearray = bytearray()
        length: int = 0

        while value > 0:
            data.append(value & 0x7F)
            value >>= 7
            if value != 0:
                data[length] |= 0x80

            length += 1

        return data

    def write_str(string: str) -> bytearray:
        if not string:
            return bytearray(b"\x00")

        data = bytearray(b"\x0B")

        data += write_uleb128(len(string.encode()))
        data += string.encode()
        return data

    path = RAGNAROK_REPLAYS_PATH / f"{score_id}.osr"

    if not path.exists():
        print(" no path")
        return

    raw = path.read_bytes()

    play = await services.database.fetch_one(
        "SELECT s.id, s.user_id, s.map_md5, s.score, s.pp, s.count_300, "
        "s.count_50, s.count_geki, s.count_katu, s.count_miss, s.count_100, "
        "s.max_combo, s.accuracy, s.perfect, s.rank, s.mods, s.mode, "
        "s.submitted FROM scores s WHERE s.id = :id LIMIT 1",
        {"id": score_id},
    )

    if not play:
        print("aSSASD")
        return

    user_info = await services.database.fetch_one(
        "SELECT username, id, privileges, passhash FROM users WHERE id = :id",
        {"id": play["user_id"]},
    )

    if not user_info:
        print("pdskaposakd")
        return

    r_hash = md5(
        f"{play["count_100"] + play["count_300"]}o{play["count_50"]}o{play["count_geki"]}o"
        f"{play["count_katu"]}t{play["count_miss"]}a{play["map_md5"]}r{play["max_combo"]}e"
        f"{bool(play["perfect"])}y{user_info["username"]}o{play["score"]}u{play["rank"]}{play["mods"]}True".encode()
    ).hexdigest()

    ret = bytearray()

    ret += struct.pack("<b", play["mode"])
    ret += struct.pack("<i", 20210520)

    ret += (
        write_str(play["map_md5"])
        + write_str(user_info["username"])
        + write_str(r_hash)
    )

    ret += struct.pack(
        "<hhhhhhih?i",
        play["count_300"],
        play["count_100"],
        play["count_50"],
        play["count_geki"],
        play["count_katu"],
        play["count_miss"],
        play["score"],
        play["max_combo"],
        play["perfect"],
        play["mods"],
    )

    ret += write_str("")

    ret += struct.pack("<qi", play["submitted"], len(raw))
    ret += raw

    ret += struct.pack("<q", play["id"])

    return ret
