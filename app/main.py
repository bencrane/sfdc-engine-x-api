from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.clients import router as clients_router
from app.routers.conflicts import router as conflicts_router
from app.routers.connections import router as connections_router
from app.routers.field_mappings import router as field_mappings_router
from app.routers.push import router as push_router
from app.routers.topology import router as topology_router
from app.routers.tokens import router as tokens_router
from app.routers.users import router as users_router
from app.config import settings
from app.db import close_pool, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool(settings.database_url)
    yield
    await close_pool()


app = FastAPI(
    title="sfdc-engine-x",
    description="Multi-tenant Salesforce administration API",
    lifespan=lifespan,
)

app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(clients_router)
app.include_router(connections_router)
app.include_router(field_mappings_router)
app.include_router(conflicts_router)
app.include_router(push_router)
app.include_router(topology_router)
app.include_router(users_router)
app.include_router(tokens_router)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
