from datetime import datetime
import services

from fastapi import Depends, Form
from fastapi.responses import ORJSONResponse
from app.api import router
from app.constants.privileges import Privileges
from app.utilities import UserData, get_current_user, log


@router.get("/admin/names/{user_id}")
async def changed_name_history(
    user_id: int,
    current_user: UserData = Depends(get_current_user),
    sorting: str = "descending",
) -> ORJSONResponse:
    if current_user is None or not current_user.privileges & Privileges.MODERATOR:
        return ORJSONResponse({"error": "insufficient permission"})

    if sorting not in ("descending", "ascending"):
        return ORJSONResponse({"error": "sorting parameter not valid"})

    sort = "DESC" if sorting == "descending" else "ASC"

    history = await services.database.fetch_all(
        "SELECT h.changed_username, h.changed_from, h.date, h.changed_by, b.username, "
        "h.id FROM name_history h INNER JOIN users b ON b.id = h.changed_by "
        f"WHERE h.user_id = :user_id ORDER BY h.date {sort}",
        {"user_id": user_id},
    )

    return ORJSONResponse([dict(name) for name in history])


@router.delete("/admin/names/{name_id}")
async def delete_name_history(
    name_id: int, current_user: UserData = Depends(get_current_user)
) -> ORJSONResponse:
    if current_user is None or not current_user.privileges & Privileges.MODERATOR:
        return ORJSONResponse({"error": "insufficient permission"})

    data = await services.database.fetch_one(
        "SELECT changed_username, user_id, changed_from, date "
        "FROM name_history WHERE id = :name_id",
        {"name_id": name_id},
    )

    if not data:
        return ORJSONResponse({"error": "name not found in history"})

    await services.database.execute(
        "DELETE FROM name_history WHERE id = :name_id", {"name_id": name_id}
    )

    readable_date = datetime.strftime(
        datetime.fromtimestamp(data["date"]), "%d/%m/%Y %H:%M:%S"
    )

    await log(
        current_user.user_id,
        f"removed the name {data["changed_username"]} from {data["user_id"]}'s history "
        f"<changed from: {data["changed_from"]}, changed to: {data["changed_username"]}, "
        f"date: {readable_date}>",
    )

    return ORJSONResponse({"response": "success"})


@router.post("/admin/names/{user_id}")
async def add_name_history(
    user_id: int,
    changed_from: str = Form(),
    changed_username: str = Form(),
    date: int = Form(),
    current_user: UserData = Depends(get_current_user),
) -> ORJSONResponse:
    if current_user is None or not current_user.privileges & Privileges.MODERATOR:
        return ORJSONResponse({"error": "insufficient permission"})

    await services.database.execute(
        "INSERT INTO name_history (user_id, changed_from, changed_username, changed_by, date) "
        "VALUES (:user_id, :changed_from, :changed_username, :changed_by, :date) ",
        {
            "changed_from": changed_from,
            "user_id": user_id,
            "changed_username": changed_username,
            "changed_by": current_user.user_id,
            "date": date,
        },
    )

    readable_date = datetime.strftime(datetime.fromtimestamp(date), "%d/%m/%Y %H:%M:%S")

    await log(
        current_user.user_id,
        f"added a name to {user_id}'s history "
        f"<changed from: {changed_from}, changed to: {changed_username}, "
        f"date: {readable_date}>",
    )

    return ORJSONResponse({"response": "success"})
