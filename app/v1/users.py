from urllib.parse import unquote
from fastapi import Depends, Query
from fastapi.responses import ORJSONResponse
from app.api import router
from app.utilities import parse_including_query, ModeAndGamemode

import services

ALLOWED_INCLUDED_FIELDS = ("clans", "stats", "achievements", "badges")

@router.get("/users/get/{user_id}")
async def user_info(
    user_id: int,
    include: list[str] = Depends(parse_including_query),
    info: ModeAndGamemode = Depends(ModeAndGamemode.parse),
) -> ORJSONResponse:
    if all(inc not in ALLOWED_INCLUDED_FIELDS for inc in include) and include != []:
        return ORJSONResponse({"error": "some or all including fields are not valid."})

    

    if not (user_info := await services.database.fetch_one(
        "SELECT username, id, registered_time, latest_activity_time, country FROM users WHERE id = :user_id OR username = :username",
        {"user_id": user_id, "username": user_id}
    )):
        return ORJSONResponse({"error": "user not found."})
    
    data = dict(user_info)

    if (session := await services.redis.hgetall(f"ragnarok:session:{user_id}")): # type: ignore
        session.pop(b"token")
        data["session"] = session
    
    if "stats" in include:
        user_stats = await services.database.fetch_one(
            f"SELECT s.{info.mode.to_db("pp")}, s.{info.mode.to_db("accuracy")}, s.{info.mode.to_db("ranked_score")}, " 
            f"s.{info.mode.to_db("total_score")}, s.{info.mode.to_db("playcount")}, s.{info.mode.to_db("playtime")}, "
            f"s.{info.mode.to_db("level")} FROM {info.gamemode.stats_table} s WHERE id = :user_id", {"user_id": user_id}
        )
        data["stats"] = dict(user_stats) # type: ignore
        
    if "clans" in include:
        clan_info = await services.database.fetch_one(
            "SELECT u.clan_id as id, c.name, c.tag, c.icon FROM users u "
            "INNER JOIN clans c ON c.id = u.clan_id "
            "WHERE u.id = :user_id ", {"user_id": user_id}
        )
        data["clan"] = dict(clan_info) # type: ignore

    if "achievements" in include:
        achievements = await services.database.fetch_all(
            "SELECT ach.id, ach.name, ach.description, ach.icon FROM users_achievements u_ach "
            "INNER JOIN achievements ach ON ach.id = u_ach.achievement_id "
            "WHERE u_ach.user_id = :user_id AND u_ach.gamemode = :gamemode AND u_ach.mode = :mode",
            {"user_id": user_id, "gamemode": info.gamemode, "mode": info.mode}
        )
        data["achievements"] = [dict(ach) for ach in achievements]

    return ORJSONResponse(data)

@router.get("/users/search")
async def search_users(query: str) -> ORJSONResponse:
    safe_query = unquote(query).lower().replace(" ", "_")

    users = await services.database.fetch_all(
        "SELECT username, id FROM users WHERE safe_username LIKE :query LIMIT 10",
        {"query": f"%{safe_query}%"}
    )

    return ORJSONResponse([dict(user) for user in users])

@router.get("/users/exists")
async def user_exists(username: str) -> ORJSONResponse:
    user = await services.database.fetch_one(
        "SELECT username, id FROM users WHERE safe_username = :query LIMIT 10",
        {"query": unquote(username).lower().replace(" ", "_")}
    )

    if not user:
        return ORJSONResponse({"error": "user not found"})

    return ORJSONResponse(dict(user))
