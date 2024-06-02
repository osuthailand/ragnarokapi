from fastapi import FastAPI
from app import init_api
import os
import services

async def startup() -> None:
    # Make sure the enviormentmeoiintal variables exists
    for env in ("DB_NAME", "DB_PASSWORD", "DB_DATABASE", "REDIS_NAME", 
                "REDIS_PASSWORD", "REDIS_HOST", "REDIS_PORT"):
        if env not in os.environ:
            services.logger.critical(f"env variable \"{env}\" has not been set.")
            exit(1)
        
    await services.database.connect()
    services.logger.info("Connected to the database.")

    await services.redis.initialize()
    services.logger.info("Connected to Redis.")

async def shutdown() -> None:
    await services.database.disconnect()
    
app = FastAPI(
    on_startup=[startup],
    on_shutdown=[shutdown]
)

app.include_router(init_api.router)