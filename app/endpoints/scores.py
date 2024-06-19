from app.constants.mods import Mods
from app.constants.privileges import Privileges
import services

from fastapi import Depends, Response
from fastapi.responses import ORJSONResponse
from app.api import router
from app.utilities import UserData, get_current_user, write_replay

import rina_pp_pyb as rosu


@router.get("/score/replay/{score_id}")
async def download_replay(score_id: int) -> Response:
    replay = await write_replay(score_id)

    if not replay:
        return ORJSONResponse(
            {"error": "no replay found or corrupted"}, status_code=404
        )

    return Response(
        bytes(replay),
        media_type="application/download",
        headers={"Content-Disposition": f'attachment;filename="{score_id}.osr";'},
    )


@router.get("/score/{score_id}")
async def get_score(
    score_id: int, current_user: UserData | None = Depends(get_current_user)
) -> ORJSONResponse:
    _base = await services.database.fetch_one(
        "SELECT id, mods, user_id, count_300, count_100, count_50, count_miss, count_geki, count_katu, "
        "pp, accuracy, score, mode, gamemode, submitted, max_combo, perfect, rank, map_md5, mode "
        "FROM scores WHERE id = :score_id",
        {"score_id": score_id},
    )

    if not _base:
        return ORJSONResponse({"error": "score not found"})

    base = dict(_base)

    beatmap_info = await services.database.fetch_one(
        "SELECT map_id, set_id, title, artist, version, cs, ar, hp, od, creator, "
        "creator_id, max_combo, mode, bpm FROM beatmaps WHERE map_md5 = :map_md5",
        {"map_md5": base["map_md5"]},
    )

    if not beatmap_info:
        return ORJSONResponse({"error": "tell simon about this. more specifically tell him 'fiks nu det her lort forhelvede din doven abe'"})

    base["beatmap"] = dict(beatmap_info)

    path_to_map = services.RAGNAROK_OSU_PATH / f"{beatmap_info["map_id"]}.osu"
    print(path_to_map.as_posix())
    rosu_map = rosu.Beatmap(path=path_to_map.as_posix())

    if base["mode"] != beatmap_info["mode"]:
        rosu_map.convert(rosu.GameMode(base["mode"]))

    mods_diff = rosu.Difficulty(mods=base["mods"]).calculate(rosu_map)
    
    # mods changing difficulty field!!
    base["beatmap"]["mods_diff"] = {
        "stars": mods_diff.stars,
        "ar": mods_diff.ar,
        "od": mods_diff.od,
        "cs": (
            min(beatmap_info["cs"] * 1.3, 10) if base["mods"] & Mods.HARDROCK else 
            max(beatmap_info["cs"] / 2, 0) if base["mods"] & Mods.EASY else 
            beatmap_info["cs"]
        ) ,
        "hp": mods_diff.hp,
    }

    # sometimes, beatmaps don't have the max_combo field 
    # filled luckily rosu calculates it aswell.
    if not base["beatmap"]["max_combo"]:
        base["beatmap"]["max_combo"]

    if (
        current_user is not None
        and current_user.privileges & Privileges.SUPPORTER
        and base["user_id"] == current_user.user_id
    ):
        viewers = await services.database.fetch_all(
            "SELECT u.username, s.user_id, s.timestamp FROM replay_views s "
            "INNER JOIN users u ON u.id = s.user_id WHERE s.score_id = :score_id",
            {"score_id": score_id},
        )
        base["viewers"] = [dict(viewer) for viewer in viewers]

    return ORJSONResponse(base)
