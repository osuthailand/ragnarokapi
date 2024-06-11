from fastapi import Depends
from fastapi.responses import ORJSONResponse
from app.constants.privileges import Privileges
from app.utilities import UserData, get_current_user
import services

from app.api import router


@router.get("/admin/friends/{user_id}")
async def users_friendlist(
    user_id: int, current_user: UserData = Depends(get_current_user)
) -> ORJSONResponse:
    if not current_user.privileges & Privileges.ADMIN:
        return ORJSONResponse({"response": "insufficient permission"})

    relationships = await services.database.fetch_all(
        "SELECT u.id, u.username, f.date, "
        "CASE WHEN mutuals.user_id1 IS NOT NULL THEN 1 ELSE 0 END AS mutual "  # <-- poop
        "FROM friends f "
        "INNER JOIN users u ON u.id = f.user_id2 "
        "LEFT JOIN friends mutuals ON f.user_id1 = mutuals.user_id2 AND f.user_id2 = mutuals.user_id1 "
        "WHERE f.user_id1 = :user_id ",
        {"user_id": user_id},
    )

    return ORJSONResponse([dict(relationship) for relationship in relationships])


# TODO: create and delete friend
