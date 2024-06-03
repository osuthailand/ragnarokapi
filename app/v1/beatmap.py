import asyncio
import os
from pathlib import Path
import aiohttp
from typing import Any

from fastapi import Depends
from fastapi import Query
from fastapi.responses import ORJSONResponse
from app.api import router
from app.utilities import ModeAndGamemode
import services

RAGNAROK_OSU_PATH = Path(os.environ["RAGNAROK_BEATMAP_PATH"])


async def save_beatmap_file(map_id: int) -> None:
    """Saves a beatmap's .osu file to ragnarok."""
    path = RAGNAROK_OSU_PATH / f"{map_id}.osu"
    if not path.exists():
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                f"https://osu.ppy.sh/web/osu-getosufile.php?q={map_id}",
                headers={"user-agent": "osu!"},
            ) as req:
                if not (resp := await req.text()):
                    services.logger.critical(
                        f"Couldn't fetch the .osu file of {map_id}. Maybe because api rate limit?"
                    )
                    return

                with path.open("w+") as osu:
                    osu.write(resp)

                services.logger.info(f"Saved {map_id}.osu to {RAGNAROK_OSU_PATH!r}")


def dictify_map(resp: dict[str, str], present_set: bool = False) -> dict[str, Any]:
    """Converts osu-api beatmaps response to a dictionary, that can be saved into the database, aswell as be saved to the database."""
    return {
        "set_id": int(resp["beatmapset_id"]),
        "map_id": int(resp["beatmap_id"]),
        "map_md5": resp["file_md5"],
        "title": resp["title"],
        "title_unicode": resp["title_unicode"] or resp["title"],
        "version": resp["version"],
        "artist": resp["artist"],
        "artist_unicode": resp["artist_unicode"] or resp["artist"],
        "creator": resp["creator"],
        "creator_id": int(resp["creator_id"]),
        "stars": float(resp["difficultyrating"]),
        "od": float(resp["diff_overall"]),
        "ar": float(resp["diff_approach"]),
        "hp": float(resp["diff_drain"]),
        "cs": float(resp["diff_size"]),
        "bpm": float(resp["bpm"]),
        "mode": int(resp["mode"]),
        "max_combo": (0 if resp["max_combo"] is None else int(resp["max_combo"])),
        "approved": int(resp["approved"]),
        "submit_date": resp["submit_date"],
        "approved_date": ("0" if not resp["approved_date"] else resp["approved_date"]),
        "latest_update": resp["last_update"],
        "length": float(resp["total_length"]),
        "drain": int(resp["hit_length"]),
        "plays": 0,
        "passes": 0,
        "favorites": 0,
        "rating": float(resp["rating"]),
        "full_set_present": int(present_set),
    }


async def save_map(map_dict: dict[str, Any]) -> None:
    """Saves a beatmap to the database"""
    # alter approved status, to match ragnarok's prefered approved status.

    # LOVED -> 5
    # QUALIFIED -> 4
    # APPROVED -> 3
    # RANKED -> 2
    ragnarok_approved = {4: 5, 3: 4, 2: 3, 1: 2}

    if map_dict["approved"] in ragnarok_approved:
        map_dict["approved"] = ragnarok_approved[map_dict["approved"]]

    await services.database.execute(
        "INSERT INTO beatmaps (server, set_id, map_id, map_md5, title, title_unicode, "
        "version, artist, artist_unicode, creator, creator_id, stars, od, ar, hp, cs, "
        "mode, bpm, max_combo, submit_date, approved_date, latest_update, length, "
        "drain, plays, passes, favorites, rating, approved, full_set_present) "
        "VALUES ('bancho', :set_id, :map_id, :map_md5, :title, :title_unicode, :version, "
        ":artist, :artist_unicode, :creator, :creator_id, :stars, :od, :ar, :hp, :cs, "
        ":mode, :bpm, :max_combo, :submit_date, :approved_date, :latest_update, :length, "
        ":drain, :plays, :passes, :favorites, :rating, :approved, :full_set_present)",
        map_dict,
    )

    asyncio.create_task(save_beatmap_file(map_dict["map_id"]))


async def get_beatmap(
    map_id: int | None = None, set_id: int | None = None, auto_save: bool = True
) -> dict[str, Any] | list[dict[str, Any]]:
    """Gets all beatmaps or a single beatmap from the osu-api"""
    if not (map_id or set_id):
        return {}

    params = ("s", set_id) if set_id else ("b", map_id)

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://osu.ppy.sh/api/get_beatmaps?{params[0]}={params[1]}&k={services.osu_key}"
        ) as req:
            if req.status != 200:
                services.logger.warn(
                    f"beatmap (set_id: {set_id}, map_id: {map_id}) could not be found in the osu api."
                )
                return {}

            resp = await req.json()

            if set_id:
                maps = []
                for map in resp:
                    dictified_map = dictify_map(map, present_set=True)
                    maps.append(dictified_map)

                    if auto_save:
                        # as the whole set is being saved, the full_set_present field, should be true.
                        await save_map(dictified_map)

                return maps

            dictified_map = dictify_map(resp)

            if auto_save:
                await save_map(dictified_map)

            return dictified_map


async def ensure_full_set(
    _data: list[dict[str, Any]], set_id: int
) -> list[dict[str, Any]]:
    """Ensures all the beatmaps, in the set, is present in the database."""
    data = _data.copy()
    # whole beatmap set is already present in database, no need for further action.
    if data[0]["full_set_present"]:
        return data

    maps = await get_beatmap(set_id=set_id, auto_save=False)
    assert type(maps) == list

    # the whole beatmap set is present, update field.
    if len(maps) == len(data):
        await services.database.execute(
            "UPDATE beatmaps SET full_set_present = 1 WHERE set_id = :set_id",
            {"set_id": set_id},
        )
        return data

    new_maps = []
    for map in maps:
        exists = (False, "")

        for rina_map in data:
            if rina_map["map_id"] == map["map_id"]:
                exists = (True, rina_map["map_md5"])
                break

        if exists[0]:
            # compare beatmap hashes, and make sure the existed
            # beatmap is up to date.
            if exists[1] != map["map_md5"]:
                # delete previous data
                await services.database.execute(
                    "DELETE FROM beatmaps WHERE map_id = :map_id",
                    {"map_id": map["map_id"]},
                )
            else:
                continue

        # save beatmap
        await save_map(map)
        new_maps.append(map)

    # update previous maps, where the `full_set_present` value was set to false
    await services.database.execute(
        "UPDATE beatmaps SET full_set_present = 1  "
        "WHERE set_id = :set_id AND full_set_present = 0 ",
        {"set_id": set_id},
    )
    services.logger.info(
        f"Saved {len(maps) - len(data)} beatmaps, so the full set is in the database."
    )

    data.extend(new_maps)
    return data


@router.get("/beatmap/set/{set_id}")
async def beatmap_set(set_id: int) -> ORJSONResponse:
    _data = await services.database.fetch_all(
        "SELECT set_id, map_id, map_md5, title, title_unicode, version, artist, "
        "artist_unicode, creator, creator_id, stars, od, ar, hp, cs, mode, bpm, "
        "max_combo, approved, submit_date, approved_date, latest_update, length, "
        "drain, plays, passes, favorites, rating, full_set_present FROM beatmaps "
        "WHERE set_id = :set_id",
        {"set_id": set_id},
    )

    if not _data:
        if map := await get_beatmap(set_id=set_id):
            return ORJSONResponse(map)

        return ORJSONResponse({"error": "beatmap not found."})

    data = await ensure_full_set(_data, set_id)  # type: ignore

    return ORJSONResponse([dict(map) for map in data])


@router.get("/beatmap/map/{map_id}")
async def beatmap(map_id: int) -> ORJSONResponse:
    data = await services.database.fetch_one(
        "SELECT set_id, map_id, map_md5, title, title_unicode, version, artist, "
        "artist_unicode, creator, creator_id, stars, od, ar, hp, cs, mode, bpm, "
        "max_combo, approved, submit_date, approved_date, latest_update, length, "
        "drain, plays, passes, favorites, rating, full_set_present FROM beatmaps "
        "WHERE map_id = :map_id",
        {"map_id": map_id},
    )

    if not data:
        if map := await get_beatmap(map_id=map_id):
            services.logger.info(
                "Using osu-api to display beatmap data. Beatmap has been saved into the database."
            )
            return ORJSONResponse(map)

        return ORJSONResponse({"error": "beatmap not found."})

    return ORJSONResponse(dict(data))


@router.get("/beatmap/scores/{map_id}")
async def scores(
    map_id: int,
    typeof: str = Query("overall"),
    info: ModeAndGamemode = Depends(ModeAndGamemode.parse),
) -> ORJSONResponse:
    if typeof not in ("overall", "friends", "country"):
        return ORJSONResponse({"error": "invalid leaderboard type"})

    query = (
        "SELECT s.id, s.user_id, u.username, u.country, s.score, s.pp, "
        "s.count_300, s.count_100, s.count_50, s.count_geki, s.count_katu, "
        "s.count_miss, s.max_combo, s.perfect, s.rank, s.mods, s.submitted "
        "FROM scores s INNER JOIN users u ON u.id = s.user_id "
        "INNER JOIN beatmaps b ON b.map_md5 = s.map_md5 "
        "WHERE u.privileges & 4  AND s.status = 3 AND s.mode = :mode "
        "AND s.gamemode = :gamemode AND b.map_id = :map_id "
    )
    params = {
        "mode": info.mode.value,
        "gamemode": info.gamemode.value,
        "map_id": map_id,
    }

    if typeof == "friends":
        # requires token, TODO later.
        ...

    if typeof == "country":
        # requires token, TODO later.
        ...

    query += "ORDER BY s.pp DESC LIMIT 50"
    data = await services.database.fetch_all(query, params)
    return ORJSONResponse([dict(d) for d in data])
