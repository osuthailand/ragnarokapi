from urllib.parse import unquote
from fastapi import Depends, Query
from fastapi.responses import ORJSONResponse
from app.api import router
from app.utilities import parse_including_query, ModeAndGamemode

import services


@router.get("/users/get/{user_id}")
async def user_info(
    user_id: int,
) -> ORJSONResponse:
    if not (
        user_info := await services.database.fetch_one(
            "SELECT username, id, registered_time, latest_activity_time, country, "
            "privileges, userpage_content, preferred_gamemode, preferred_mode, "
            "is_verified FROM users WHERE id = :user_id", {"user_id": user_id},
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
        {"user_id": user_id}
    )
    data["name_history"] = [dict(name) for name in name_history] if name_history else []

    return ORJSONResponse(data)


@router.get("/users/get/{user_id}/stats")
async def get_user_stats(
    user_id: int, info: ModeAndGamemode = Depends(ModeAndGamemode.parse)
) -> ORJSONResponse: 
    _data = await services.database.fetch_one(
        f"SELECT s.{info.mode.to_db("pp")}, s.{info.mode.to_db("accuracy")}, s.{info.mode.to_db("ranked_score")}, "
        f"s.{info.mode.to_db("total_score")}, s.{info.mode.to_db("playcount")}, s.{info.mode.to_db("playtime")}, "
        f"s.{info.mode.to_db("level")}, s.{info.mode.to_db("max_combo")}, u.country FROM {info.gamemode.to_db} s "
        "INNER JOIN users u ON u.id = s.id WHERE s.id = :user_id", {"user_id": user_id}
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

    data["rank"] = {
        "global": global_rank,
        "country": country_rank
    }

    return ORJSONResponse(dict(data))

@router.get("/users/get/{user_id}/achievements")
async def get_user_achievements(
    user_id: int, info: ModeAndGamemode = Depends(ModeAndGamemode.parse)
) -> ORJSONResponse:
    data = await services.database.fetch_all(
        "SELECT ach.id, ach.name, ach.description, ach.icon FROM users_achievements u_ach "
        "INNER JOIN achievements ach ON ach.id = u_ach.achievement_id "
        "WHERE u_ach.user_id = :user_id AND u_ach.gamemode = :gamemode AND u_ach.mode = :mode",
        {"user_id": user_id, "gamemode": info.gamemode, "mode": info.mode}
    )

    return ORJSONResponse([dict(achievement) for achievement in data])
    

@router.get("/users/get/{user_id}/activities")
async def get_user_recent_activities(
    user_id: int, page: int = Query(1), info: ModeAndGamemode = Depends(ModeAndGamemode.parse)
) -> ORJSONResponse:
    limit = 10 * page
    offset = 10 * (page - 1)

    data = await services.database.fetch_all(
        "SELECT a.id, a.activity, b.map_id, b.set_id, b.title, b.artist, b.version, a.timestamp " 
        "FROM recent_activities a INNER JOIN beatmaps b ON b.map_md5 = a.map_md5 WHERE a.user_id = :user_id "
        "AND a.mode = :mode AND a.gamemode = :gamemode LIMIT :limit OFFSET :offset ", 
        {
            "user_id": user_id, 
            "mode": info.mode, 
            "gamemode": info.gamemode, 
            "offset": offset, 
            "limit": limit
        }
    )

    return ORJSONResponse([dict(activity) for activity in data])

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
