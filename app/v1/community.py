import services

from fastapi import Depends, Query
from fastapi.responses import ORJSONResponse
from app.api import router
from app.utilities import ModeAndGamemode


@router.get("/community/leaderboard")
async def leaderboard(
    sort: str = Query("pp"),
    page: int = Query(1, ge=1),
    country: str | None = Query(None),
    info: ModeAndGamemode = Depends(ModeAndGamemode.parse),
) -> ORJSONResponse:
    if sort not in ("pp", "score"):
        return ORJSONResponse({"error": "invalid sorting"})

    limit = page * 50
    offset = (page - 1) * 50

    # only get the users who are in the redis range thingy yup
    # wondering if i should just ignore the users in redis, and 
    # just use a order by in the sql query?
    redis_key = f"ragnarok:leaderboard:{info.gamemode.name.lower()}:{info.mode}"
    _user_id_range = await services.redis.zrevrange(
        redis_key,
        start=0,
        end=-1,
    )

    if not _user_id_range:
        return ORJSONResponse({"users": [], "count": 0})
    
    if offset > len(_user_id_range):
        return ORJSONResponse({"users": [], "count": 0})

    user_id_range = _user_id_range[offset:limit]

    _users = await services.database.fetch_all(
        f"SELECT u.id, u.username, u.country, u.latest_activity_time, s.{info.mode.to_db("pp")}, "
        f"s.{info.mode.to_db("ranked_score")}, s.{info.mode.to_db("total_score")}, s.{info.mode.to_db("level")}, "
        f"s.{info.mode.to_db("accuracy")}, s.{info.mode.to_db("playcount")}, s.{info.mode.to_db("total_hits")} "
        f"FROM users u INNER JOIN {info.gamemode.to_db} AS s ON s.id = u.id WHERE u.id IN :user_ids ORDER BY pp DESC",
        {"user_ids": user_id_range},
    )

    users = [dict(user) for user in _users]

    for user in users:
        # maybe not so smart?? idk
        user["rank"] = await services.redis.zrevrank(redis_key, str(user["id"])) + 1

    return ORJSONResponse({"users": users, "count": len(_user_id_range)})


@router.get("/community/plays")
async def community_plays() -> ORJSONResponse: ...


@router.get("/community/pray")
async def get_prayers() -> int:
    return await services.database.fetch_val("SELECT COUNT(*) FROM prayers")


@router.post("/community/pray")
async def pray_for_rina() -> None:
    # teehee
    await services.database.execute("INSERT INTO prayers VALUES ()")
