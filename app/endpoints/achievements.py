import services

from fastapi.responses import ORJSONResponse
from app.api import router


@router.get("/achievements")
async def get_all_achievements() -> ORJSONResponse:
    achievements = await services.database.fetch_all(
        "SELECT id, name, description, icon FROM achievements"
    )

    if not achievements:
        services.logger.critical("no achievements? something is seriously wrong")
        return ORJSONResponse({"error": "no achievements"})

    return ORJSONResponse([dict(achievement) for achievement in achievements])
