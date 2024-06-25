import io
import os
import services
from fastapi import Depends, Query, UploadFile
from fastapi.responses import ORJSONResponse
from app.api import router
from app.constants.privileges import Privileges
from app.utilities import UserData, get_current_user

from PIL import Image

from services import AVATAR_PATH


def remove_previous(id: int) -> None:
    ap = AVATAR_PATH.glob(f"{id}.*")

    for a in ap:
        os.remove(a.as_posix())


@router.post("/settings/avatar")
async def set_avatar(
    avatar: UploadFile,
    current_user: UserData | None = Depends(get_current_user),
    user_id: int | None = Query(None),
) -> ORJSONResponse:
    if not current_user:
        return ORJSONResponse({"error": "unauthorized"})

    # if the user is a moderator
    # the mod can change peoples avatar
    file_type = avatar.content_type.split("/")[1]

    if current_user.privileges & Privileges.MODERATOR and user_id is not None:
        path = AVATAR_PATH / f"{user_id}.{file_type}"
        remove_previous(user_id)
    else:
        path = AVATAR_PATH / f"{current_user.user_id}.{file_type}"
        remove_previous(current_user.user_id)

    if not current_user.privileges & Privileges.SUPPORTER and file_type == "gif":
        return ORJSONResponse({"error": "insufficient permission"})

    raw_avatar = await avatar.read()
    r_avatar = Image.open(io.BytesIO(raw_avatar))

    if file_type != "gif":
        # resize avatar
        r_avatar = r_avatar.resize((256, 256))

    r_avatar.save(path.as_posix(), file_type.upper())
    return ORJSONResponse({"response": "success"})


@router.delete("/settings/avatar")
async def delete_avatar(
    current_user: UserData | None = Depends(get_current_user),
    user_id: int | None = Query(None),
) -> ORJSONResponse:
    if not current_user:
        return ORJSONResponse({"error": "unauthorized"})

    if current_user.privileges & Privileges.MODERATOR and user_id is not None:
        remove_previous(user_id)
    else:
        remove_previous(current_user.user_id)

    return ORJSONResponse({"response": "success"})


@router.get("/friendship/{user_id}")
async def get_friendship_status(
    user_id: int,
    current_user: UserData | None = Depends(get_current_user),
) -> ORJSONResponse:
    if not current_user:
        return ORJSONResponse({"error": "unauthorized"})

    status = await services.database.fetch_val(
        "SELECT CASE WHEN mutuals.user_id1 IS NOT NULL THEN 1 ELSE 0 END AS mutual "
        "FROM friends f LEFT JOIN friends mutuals ON f.user_id1 = mutuals.user_id2 AND f.user_id2 = mutuals.user_id1 "
        "WHERE f.user_id1 = :my_id AND f.user_id2 = :user_id LIMIT 1",
        {"my_id": current_user.user_id, "user_id": user_id},
    )

    if status is None:
        status = -1

    return ORJSONResponse({"status": status})


@router.post("/friendship/{user_id}")
async def add_friend(
    user_id: int,
    current_user: UserData | None = Depends(get_current_user),
) -> ORJSONResponse:
    if not current_user:
        return ORJSONResponse({"error": "unauthorized"})

    await services.database.execute(
        "INSERT INTO friends (user_id1, user_id2) VALUES (:my_id, :user_id)",
        {"my_id": current_user.user_id, "user_id": user_id},
    )

    return ORJSONResponse({"status": "success"})


@router.delete("/friendship/{user_id}")
async def remove_friend(
    user_id: int,
    current_user: UserData | None = Depends(get_current_user),
) -> ORJSONResponse:
    if not current_user:
        return ORJSONResponse({"error": "unauthorized"})

    await services.database.execute(
        "DELETE FROM friends WHERE user_id1 = :my_id AND user_id2 = :user_id",
        {"my_id": current_user.user_id, "user_id": user_id},
    )

    return ORJSONResponse({"status": "success"})
