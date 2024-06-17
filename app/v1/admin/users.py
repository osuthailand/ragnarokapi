import math
from urllib.parse import unquote

from fastapi import Depends, Query
from app.constants.privileges import Privileges
from app.utilities import UserData, get_current_user
import services

from fastapi.responses import ORJSONResponse
from app.api import router


@router.get("/admin/users")
async def admin_users(
    current_user: UserData = Depends(get_current_user),
    search: str = Query(""),
    country: str = Query(""),
    entries: int = Query(50, ge=1),
    page: int = Query(1, ge=1),
) -> ORJSONResponse:
    if not current_user.privileges & Privileges.MODERATOR:
        return ORJSONResponse({"error": "insufficient permission"})

    safe_search = unquote(search).lower().replace(" ", "_")
    offset = (page - 1) * entries
    query = "SELECT username, id, country, privileges, registered_time, privileges FROM users WHERE safe_username LIKE :search "
    count_query = "SELECT COUNT(*) FROM users WHERE safe_username LIKE :search "
    params = {"search": f"%{safe_search}%"}

    if country:
        query += "AND country = :country "
        count_query += "AND country = :country "
        params["country"] = country

    query += "LIMIT :limit OFFSET :offset"
    params |= {"limit": entries, "offset": offset}
    users = await services.database.fetch_all(query, params)

    params.pop("limit")
    params.pop("offset")
    max_users_from_search = await services.database.fetch_val(count_query, params)

    max_pages = math.ceil(max_users_from_search / entries)

    return ORJSONResponse(
        {
            "max_pages": max_pages,
            "max_users": max_users_from_search,
            "users": [dict(user) for user in users],
        }
    )
