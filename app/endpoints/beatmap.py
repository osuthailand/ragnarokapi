from fastapi import Depends
from fastapi import Query
from fastapi.responses import ORJSONResponse
from app.api import router
from app.objects.beatmaps import Beatmap
from app.utilities import ModeAndGamemode, UserData, get_current_user
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
    current_user: UserData | None = Depends(get_current_user),
) -> ORJSONResponse:
    if typeof not in ("overall", "friends", "country", "local"):
        return ORJSONResponse({"error": "invalid leaderboard type"})

    # i ran into some problems when using joins or subqueries
    # to get the map_md5 with map_id as identifier.
    subquery = """
    SELECT
        map_md5
    FROM beatmaps
    WHERE map_id = :map_id
    """
    subparams = {"map_id": map_id}
    map_md5 = await services.database.fetch_val(subquery, subparams)

    if not map_md5:
        return ORJSONResponse({"error": "beatmap not found"})

    # with the help from someone, we came up with this query
    # it's pretty weird and somewhat slow (2-1 seconds load)
    # compared to just fetching it normally (5-7 seconds load)
    # keeping this just so i can look at it lul
    # query = """
    # SELECT
    #     `s`.`id`, `s`.`user_id`, `u`.`username`, `u`.`country`, `s`.`score`, `s`.`pp`,
    #     `s`.`count_300`, `s`.`count_100`, `s`.`count_50`, `s`.`count_geki`,
    #     `s`.`count_katu`, `s`.`count_miss`, `s`.`max_combo`, `s`.`perfect`,
    #     `s`.`rank`, `s`.`mods`, `s`.`submitted`
    # FROM `scores` `m` FORCE INDEX (md5_mode_gm_status)
    # INNER JOIN `scores` `s`
    #     ON `m`.`id` = `s`.`id`
    # INNER JOIN `users` `u`
    #     ON `u`.`id` = `s`.`user_id`
    # INNER JOIN `beatmaps` `b`
    #     ON `b`.`map_md5` = `s`.`map_md5`
    # WHERE `m`.`map_md5` = (SELECT `map_md5` FROM `beatmaps` WHERE `map_id` = :map_id LIMIT 1)
    # AND `u`.`privileges` & 4
    # AND `m`.`gamemode` = :gamemode
    # AND `m`.`mode` = :mode
    # AND `m`.`status` = 3
    # """

    query = """
    SELECT
        `s`.`id`, `s`.`user_id`, `u`.`username`, `u`.`country`, `s`.`score`, `s`.`pp`,
        `s`.`count_300`, `s`.`count_100`, `s`.`count_50`, `s`.`count_geki`,
        `s`.`count_katu`, `s`.`count_miss`, `s`.`max_combo`, `s`.`perfect`,
        `s`.`rank`, `s`.`mods`, `s`.`submitted`, `s`.`accuracy`
    FROM `scores` `s`
    INNER JOIN `users` `u`
        ON `u`.`id` = `s`.`user_id`
    WHERE `s`.`map_md5` = :map_md5
    AND `u`.`privileges` & 4
    AND `s`.`gamemode` = :gamemode
    AND `s`.`mode` = :mode
    """

    params = {
        "mode": info.mode.value,
        "gamemode": info.gamemode.value,
        "map_md5": map_md5,
    }

    if typeof == "local" and current_user:
        query += """
        AND `u`.`id` = :user_id
        AND `s`.`status` >= 2
        """
        params["user_id"] = current_user.user_id
    else:
        query += """
            AND `s`.`status` = 3
        """

    if typeof == "friends" and current_user:
        query += """
        AND `u`.`id` IN (SELECT `user_id2` FROM `friends` WHERE `user_id1` = :user_id)
        """
        params["user_id"] = current_user.user_id

    if typeof == "country" and current_user:
        query += """
        AND `u`.`country` = (SELECT `country` FROM users WHERE `id` = :user_id LIMIT 1)
        """
        params["user_id"] = current_user.user_id

    query += f"ORDER BY `s`.`{info.gamemode.score_order}` DESC LIMIT 50"
    data = await services.database.fetch_all(query, params)
    return ORJSONResponse([dict(d) for d in data])
