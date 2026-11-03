from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def today_brussels() -> date:
    """« Aujourd'hui » au sens du calendrier belge (section 5)."""
    return datetime.now(ZoneInfo(get_settings().timezone)).date()
