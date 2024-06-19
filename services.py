import logging
from pathlib import Path
from databases import Database
from redis import asyncio as aioredis
import os

database = Database(f"mysql+aiomysql://{os.getenv("DB_NAME")}:{os.getenv("DB_PASSWORD")}@localhost/{os.getenv("DB_DATABASE")}")
redis = aioredis.from_url(
    f"redis://{os.getenv("REDIS_NAME")}:{os.getenv("REDIS_PASSWORD")}@{os.getenv("REDIS_HOST")}:{os.getenv("REDIS_PORT")}"
)

logger = logging.getLogger("uvicorn.error")
osu_key = os.environ["OSU_API_KEY"]

RAGNAROK_OSU_PATH = Path(os.environ["RAGNAROK_BEATMAP_PATH"])
AVATAR_PATH = Path(os.getenv("RAGNAROK_AVATAR_PATH"))

