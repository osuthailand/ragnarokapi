from urllib.parse import unquote
from fastapi import Depends, Query
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
from app.api import router
from app.utilities import parse_including_query, ModeAndGamemode

import services


@router.get("/users/get/{user_id}")
async def user_info(
    user_id: int,
) -> ORJSONResponse:
    if not (
        user_info := await services.database.fetch_one(
            "SELECT username, id, registered_time, latest_activity_time, country, playstyles, "
            "privileges, userpage_content, preferred_gamemode, preferred_mode, is_verified, "
            "latest_activity_time FROM users WHERE id = :user_id",
            {"user_id": user_id},
        )
    ):
        return ORJSONResponse({"error": "user not found."})

    data = dict(user_info)

    if session := await services.redis.hgetall(f"ragnarok:session:{user_id}"):  # type: ignore
        session.pop(b"token")
        data["session"] = {
            key.decode(): value.decode() for key, value in session.items()
        }

    clan_info = await services.database.fetch_one(
        "SELECT u.clan_id as id, c.name, c.tag, c.icon FROM users u "
        "INNER JOIN clans c ON c.id = u.clan_id "
        "WHERE u.id = :user_id ",
        {"user_id": user_id},
    )

    data["clan"] = dict(clan_info) if clan_info else {}

    name_history = await services.database.fetch_all(
        "SELECT changed_from, changed_username, date FROM name_history WHERE user_id = :user_id",
        {"user_id": user_id},
    )
    data["name_history"] = [dict(name) for name in name_history] if name_history else []

    return ORJSONResponse(data)


@router.get("/users/history/{user_id}")
async def get_user_history(
    user_id: int,
    graph: str = Query(regex="pp|rank"),
    info: ModeAndGamemode = Depends(ModeAndGamemode.parse),
) -> ORJSONResponse:
    graph_data = await services.database.fetch_all(
        f"SELECT {graph}, timestamp FROM profile_history WHERE mode = :mode "
        "AND gamemode = :gamemode AND user_id = :user_id ORDER BY timestamp DESC "
        "LIMIT 90",
        {
            "mode": info.mode,
            "gamemode": info.gamemode,
            "user_id": user_id,
        },
    )

    if not graph_data:
        return ORJSONResponse([])

    data = [dict(d) for d in graph_data]
    last_type_update = data[0]

    if graph == "pp":
        should_update = await services.database.fetch_val(
            f"SELECT CAST({info.mode.to_db("pp", False)} AS INT) AS pp FROM {info.gamemode.to_db} "
            f" WHERE id = :user_id AND {info.mode.to_db("pp", False)} != :last_pp ",
            {
                "user_id": user_id,
                "last_pp": last_type_update["pp"],
            },
        )

        if should_update:
            await services.database.execute(
                "UPDATE profile_history SET pp = :new_pp "
                "WHERE gamemode = :gamemode AND mode = :mode "
                "AND user_id = :user_id AND timestamp = :timestamp ",
                {
                    "new_pp": should_update,
                    "gamemode": info.gamemode,
                    "mode": info.mode,
                    "user_id": user_id,
                    "timestamp": last_type_update["timestamp"],
                },
            )

            last_type_update["pp"] = should_update

    elif graph == "rank":
        _current_global_rank = await services.redis.zrevrank(
            f"ragnarok:leaderboard:{info.gamemode.name.lower()}:{info.mode}",
            str(user_id),
        )
        current_global_rank = (
            _current_global_rank + 1 if _current_global_rank is not None else 0
        )

        if current_global_rank != last_type_update["rank"]:
            await services.database.execute(
                "UPDATE profile_history SET rank = :new_rank "
                "WHERE gamemode = :gamemode AND mode = :mode "
                "AND user_id = :user_id AND timestamp = :timestamp ",
                {
                    "new_rank": current_global_rank,
                    "gamemode": info.gamemode,
                    "mode": info.mode,
                    "user_id": user_id,
                    "timestamp": last_type_update["timestamp"],
                },
            )

            last_type_update["rank"] = current_global_rank

    return ORJSONResponse(data)


class Grades(BaseModel):
    XH: int = 0
    X: int = 0
    SH: int = 0
    S: int = 0
    A: int = 0
    B: int = 0
    C: int = 0
    D: int = 0
    F: int = 0


@router.get("/users/get/{user_id}/stats")
async def get_user_stats(
    user_id: int, info: ModeAndGamemode = Depends(ModeAndGamemode.parse)
) -> ORJSONResponse:
    _data = await services.database.fetch_one(
        f"SELECT s.{info.mode.to_db("pp")}, s.{info.mode.to_db("accuracy")}, s.{info.mode.to_db("ranked_score")}, "
        f"s.{info.mode.to_db("total_score")}, s.{info.mode.to_db("playcount")}, s.{info.mode.to_db("playtime")}, "
        f"s.{info.mode.to_db("level")}, s.{info.mode.to_db("max_combo")}, s.{info.mode.to_db("replays_watched_by_others")}, "
        f"u.country FROM {info.gamemode.to_db} s INNER JOIN users u ON u.id = s.id WHERE s.id = :user_id",
        {"user_id": user_id},
    )

    if not _data:
        return ORJSONResponse({"error": "user doens't exist."})

    data = dict(_data)

    global_redis_key = f"ragnarok:leaderboard:{info.gamemode.name.lower()}:{info.mode}"
    country_redis_key = f"ragnarok:leaderboard:{info.gamemode.name.lower()}:{data["country"]}:{info.mode}"

    _global_rank = await services.redis.zrevrank(global_redis_key, str(user_id))
    global_rank = _global_rank + 1 if _global_rank is not None else 0

    _country_rank = await services.redis.zrevrank(country_redis_key, str(user_id))
    country_rank = _country_rank + 1 if _country_rank is not None else 0

    data["rank"] = {"global": global_rank, "country": country_rank}

    rank_counter = await services.database.fetch_all(
        "SELECT COUNT(rank) AS count, rank FROM scores WHERE gamemode = :gamemode "
        "AND mode = :mode AND status = 3 AND user_id = :user_id GROUP BY rank",
        {"gamemode": info.gamemode, "mode": info.mode, "user_id": user_id},
    )

    data["grades"] = Grades(
        **{grade["rank"]: grade["count"] for grade in rank_counter}
    ).model_dump()

    return ORJSONResponse(dict(data))


@router.get("/users/get/{user_id}/achievements")
async def get_user_achievements(
    user_id: int, info: ModeAndGamemode = Depends(ModeAndGamemode.parse)
) -> ORJSONResponse:
    data = await services.database.fetch_all(
        "SELECT ach.id, ach.name, ach.description, ach.icon FROM users_achievements u_ach "
        "INNER JOIN achievements ach ON ach.id = u_ach.achievement_id "
        "WHERE u_ach.user_id = :user_id AND u_ach.gamemode = :gamemode AND u_ach.mode = :mode",
        {"user_id": user_id, "gamemode": info.gamemode, "mode": info.mode},
    )

    return ORJSONResponse([dict(achievement) for achievement in data])


@router.get("/users/get/{user_id}/activities")
async def get_user_recent_activities(
    user_id: int,
    page: int = Query(1, ge=1),
    info: ModeAndGamemode = Depends(ModeAndGamemode.parse),
) -> ORJSONResponse:
    offset = 10 * (page - 1)

    data = await services.database.fetch_all(
        "SELECT a.id, a.activity, b.map_id, b.set_id, b.title, b.artist, b.version, a.timestamp "
        "FROM recent_activities a INNER JOIN beatmaps b ON b.map_md5 = a.map_md5 WHERE a.user_id = :user_id "
        "AND a.mode = :mode AND a.gamemode = :gamemode LIMIT 10 OFFSET :offset ",
        {
            "user_id": user_id,
            "mode": info.mode,
            "gamemode": info.gamemode,
            "offset": offset,
        },
    )

    return ORJSONResponse([dict(activity) for activity in data])


@router.get("/users/scores/{user_id}/best")
async def get_users_best(
    user_id: int,
    page: int = Query(1, ge=1),
    info: ModeAndGamemode = Depends(ModeAndGamemode.parse),
) -> ORJSONResponse:
    offset = 10 * (page - 1)
    scores = await services.database.fetch_all(
        "SELECT s.id, b.title, b.artist, b.version, b.set_id, b.map_id, s.submitted, s.max_combo, "
        "s.mods, s.pp, s.accuracy, s.count_miss, s.count_50, s.count_100, s.count_300, s.rank, "
        "s.count_geki, s.count_katu, s.score FROM scores s INNER JOIN beatmaps b ON b.map_md5 = s.map_md5 "
        "WHERE s.status = 3 AND s.awards_pp = 1 AND s.gamemode = :gamemode AND s.mode = :mode "
        "AND s.user_id = :user_id ORDER BY s.pp DESC LIMIT 10 OFFSET :offset",
        {
            "user_id": user_id,
            "gamemode": info.gamemode,
            "mode": info.mode,
            "offset": offset,
        },
    )

    return ORJSONResponse([dict(score) for score in scores])


@router.get("/users/scores/{user_id}/recent")
async def get_users_recent(
    user_id: int,
    page: int = Query(1, ge=1),
    info: ModeAndGamemode = Depends(ModeAndGamemode.parse),
) -> ORJSONResponse:
    offset = 10 * (page - 1)
    scores = await services.database.fetch_all(
        "SELECT s.id, b.title, b.artist, b.version, b.set_id, b.map_id, s.submitted, s.max_combo, "
        "s.mods, s.pp, s.accuracy, s.count_miss, s.count_50, s.count_100, s.count_300, s.rank, "
        "s.count_geki, s.count_katu, s.score FROM scores s INNER JOIN beatmaps b ON b.map_md5 = s.map_md5 "
        "WHERE s.gamemode = :gamemode AND s.mode = :mode AND s.user_id = :user_id ORDER BY s.submitted DESC "
        "LIMIT 10 OFFSET :offset",
        {
            "user_id": user_id,
            "gamemode": info.gamemode,
            "mode": info.mode,
            "offset": offset,
        },
    )

    return ORJSONResponse([dict(score) for score in scores])


@router.get("/users/search")
async def search_users(query: str) -> ORJSONResponse:
    safe_query = unquote(query).lower().replace(" ", "_")

    users = await services.database.fetch_all(
        "SELECT username, id, country FROM users WHERE safe_username LIKE :query LIMIT 10",
        {"query": f"%{safe_query}%"},
    )

    return ORJSONResponse([dict(user) for user in users])


@router.get("/users/exists")
async def user_exists(username: str) -> ORJSONResponse:
    user = await services.database.fetch_one(
        "SELECT username, id FROM users WHERE safe_username = :query LIMIT 10",
        {"query": unquote(username).lower().replace(" ", "_")},
    )

    if not user:
        return ORJSONResponse({"error": "user not found"})

    return ORJSONResponse(dict(user))
