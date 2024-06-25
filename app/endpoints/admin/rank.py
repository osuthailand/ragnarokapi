from fastapi import Depends, Form
from fastapi.responses import ORJSONResponse
from app.constants.approved import Approved
from app.constants.privileges import Privileges
from app.utilities import UserData, get_current_user, log
import services

from app.api import router


@router.post("/admin/rank")
async def users_friendlist(
    map_md5: str = Form(),
    new_status: int = Form(),
    current_user: UserData | None = Depends(get_current_user),
) -> ORJSONResponse:
    if current_user is None or not current_user.privileges & Privileges.BAT:
        return ORJSONResponse({"response": "insufficient permission"}, status_code=401)

    # ensure the beatmap even exists.
    if not (
        beatmap := await services.database.fetch_one(
            "SELECT approved, title, artist, version FROM beatmaps WHERE map_md5 = :map_md5",
            {"map_md5": map_md5},
        )
    ):
        return ORJSONResponse({"error": "beatmap doesn't exist."}, status_code=404)

    # ensure the status is possible, ignoring the update value.
    if new_status not in (-2, -1, 0, 2, 3, 4, 5):
        return ORJSONResponse({"error": "invalid status"}, status_code=400)

    ranked_status = Approved(new_status)

    # just ignore the request, if the status is the same.
    if ranked_status == Approved(beatmap["approved"]):
        return ORJSONResponse({"response": "ignoring"})

    # if the new status doesn't award pp, make sure
    # we update all scores on the beatmap where the
    # awards pp field is set to true.
    if not ranked_status.awards_pp:
        await services.database.execute(
            "UPDATE scores SET awards_pp = 0 WHERE map_md5 = :map_md5",
            {"map_md5": map_md5},
        )

    await services.database.execute(
        "UPDATE beatmaps SET approved = :approved WHERE map_md5 = :map_md5",
        {"approved": ranked_status.value, "map_md5": map_md5},
    )

    await log(
        user_id=current_user.user_id, 
        note=f"has updated {beatmap["artist"]} - {beatmap["title"]} ({beatmap["version"]})'s "
             f"ranked status from {Approved(beatmap["approved"]).name.lower()} to {ranked_status.name.lower()}"
    )

    return ORJSONResponse({"response": "ok"})
