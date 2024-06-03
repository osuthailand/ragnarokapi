from fastapi.responses import ORJSONResponse
from app.api import router


@router.route("/settings/avatar", methods=["POST", "PUT"])
async def set_avatar() -> ORJSONResponse:
    return ORJSONResponse({"response": "success"})
