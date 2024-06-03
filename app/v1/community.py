from typing import Any

from fastapi import Depends, Query
from fastapi.responses import ORJSONResponse
from app.api import router
from app.utilities import ModeAndGamemode


@router.get("/community/leaderboard")
async def leaderboard(
    sort: str = Query("pp"),
    page: int = Query(1, ge=1),
    country: str | None = Query(None),
    info: ModeAndGamemode = Depends(ModeAndGamemode.parse),
) -> ORJSONResponse: ...


@router.get("/community/plays")
async def community_plays() -> ORJSONResponse: ...
