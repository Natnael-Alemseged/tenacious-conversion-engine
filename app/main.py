from fastapi import FastAPI

from app.api.routes.bookings import router as booking_router
from app.api.routes.health import router as health_router
from app.api.routes.webhooks import router as webhook_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(booking_router, prefix="/bookings", tags=["bookings"])
app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
