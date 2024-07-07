from fastapi import Depends
from fastapi import Query
from fastapi.responses import ORJSONResponse
from app.api import router
from app.objects.beatmaps import Beatmap
from app.utilities import ModeAndGamemode
import services


@router.get("/beatmap/set/{set_id}")
async def beatmap_set(set_id: int):
    from_sql = await Beatmap.from_sql(set_id=set_id)

    if not from_sql:
        if map := await Beatmap.from_api(set_id=set_id):
            return map

        return ORJSONResponse({"error": "beatmap not found."})

    data = await Beatmap.ensure_full_set(from_sql)  # type: ignore

    return data


@router.get("/beatmap/map/{map_id}")
async def beatmap(map_id: int):
    from_sql = await Beatmap.from_sql(map_id=map_id)

    if not from_sql:
        if map := await Beatmap.from_api(map_id=map_id):
            services.logger.info(
                "Using osu-api to display beatmap data. Beatmap has been saved into the database."
            )
            return map

        return ORJSONResponse({"error": "beatmap not found."})

    return from_sql


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
