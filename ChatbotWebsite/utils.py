from datetime import datetime
from zoneinfo import ZoneInfo

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")

def now_nepal():
    return datetime.now(NEPAL_TZ)