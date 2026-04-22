from fastapi import FastAPI

from agent.api.routes.bookings import router as booking_router
from agent.api.routes.health import router as health_router
from agent.api.routes.webhooks import router as webhook_router
from agent.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(booking_router, prefix="/bookings", tags=["bookings"])
app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
