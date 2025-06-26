from fastapi import FastAPI
import app_context as ac
import logging
import uvicorn

app = FastAPI(
    title="LadderChicken API",
    description="API for the LadderChicken project",
)

logger = logging.getLogger("fastapi")

@app.get("/")
def read_root():
    return {"Hello": "World"}


async def main():
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=58011,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()