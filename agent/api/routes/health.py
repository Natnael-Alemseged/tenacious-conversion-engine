from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def root() -> dict[str, object]:
    return {
        "service": "Conversion Engine",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
