import services

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


@router.get("/community/pray")
async def get_prayers() -> int:
    return await services.database.fetch_val("SELECT COUNT(*) FROM prayers")


@router.post("/community/pray")
async def pray_for_rina() -> None:
    # teehee
    await services.database.execute("INSERT INTO prayers VALUES ()")
