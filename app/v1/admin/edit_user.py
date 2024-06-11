import services

from fastapi import Depends, Form
from fastapi.responses import ORJSONResponse
from app.api import router
from app.constants.privileges import Privileges
from app.utilities import UserData, get_current_user, log


@router.post("/edit/user/{user_id}")
async def edit_user_field(
    user_id: int,
    field: str = Form(),
    value: str | int = Form(),
    current_user: UserData = Depends(get_current_user),
) -> ORJSONResponse:
    # TODO: other fields requires different privileges
    if not current_user.privileges & Privileges.ADMIN:
        return ORJSONResponse({"error": "insufficient permission"})

    if field not in ("userpage_content", "country", "username", "notes", "privileges"):
        return ORJSONResponse({"error": "invalid field"})

    query = "UPDATE users SET "
    params = {}

    match field:
        case "username":
            assert type(value) == str
            query += "username = :username, safe_username = :safe_uname "
            params |= {"username": value, "safe_uname": value.lower().replace(" ", "_")}

        case "userpage_content":
            query += "userpage_content = :userpage_content "
            params["userpage_content"] = value

        case "notes":
            query += "notes = :notes "
            params["notes"] = value

        case "privileges":
            query += "privileges = :privileges "
            params["privileges"] = value

        case "country":
            query += "country = :country "
            params["country"] = value

        case "email":
            query += "email = :email"
            params["email"] = value

    query += "WHERE id = :user_id"
    params["user_id"] = user_id

    await services.database.execute(query, params)

    note = f"updated user {user_id}'s {field} to {value:.20}"
    await log(current_user.user_id, note)

    return ORJSONResponse({"response": "success"})
