import services
from fastapi.responses import ORJSONResponse
from app.api import router


@router.get("/docs")
async def get_all_docs() -> ORJSONResponse:
    docs = await services.database.fetch_all("SELECT * FROM docs")

    if not docs:
        return ORJSONResponse({"error": "what the sigma"})

    return ORJSONResponse([dict(doc) for doc in docs])


@router.get("/docs/get/{url}")
async def get_doc(url: str) -> ORJSONResponse:
    doc = await services.database.fetch_one(
        "SELECT * FROM docs WHERE url = :url", {"url": url}
    )

    if not doc:
        return ORJSONResponse({"error": "doc not found"}, status_code=404)

    return ORJSONResponse(dict(doc))
