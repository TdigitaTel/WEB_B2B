"""Global, persistent refresh interval for the web's read views."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .auth import audit, require_roles
from .db import get_db
from .models import ScreenRefreshSettings, User

router = APIRouter(tags=["screen-refresh"])


class RefreshSettingsIn(BaseModel):
    interval_seconds: int = Field(default=5, ge=5, le=300, strict=True)


@router.get("/api/v1/screen-refresh-settings")
def read_settings(db: Session = Depends(get_db)):
    # Public metadata only: needed by the login screen too. No business data.
    row = db.get(ScreenRefreshSettings, 1)
    return {"interval_seconds": row.interval_seconds if row else 5}


@router.patch("/api/v1/store/screen-refresh-settings")
def update_settings(data: RefreshSettingsIn,
                    user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")),
                    db: Session = Depends(get_db)):
    row = db.get(ScreenRefreshSettings, 1)
    if row is None:
        row = ScreenRefreshSettings(id=1)
        db.add(row)
    row.interval_seconds = data.interval_seconds
    audit(db, user, "SCREEN_REFRESH_SETTINGS_UPDATED", "SCREEN_REFRESH_SETTINGS", metadata=data.model_dump())
    db.commit()
    return {"interval_seconds": row.interval_seconds}
