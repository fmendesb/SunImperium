# sun_imperium_app/utils/state.py
import time
import httpx
from datetime import datetime, timezone

def _execute_with_retry(req, tries: int = 4, base_sleep: float = 0.6):
    last = None
    for i in range(tries):
        try:
            return req.execute()
        except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last = e
            time.sleep(base_sleep * (2 ** i))
        except Exception as e:
            msg = str(e).lower()
            if "resource temporarily unavailable" in msg or "readerror" in msg:
                last = e
                time.sleep(base_sleep * (2 ** i))
            else:
                raise
    raise last

def ensure_bootstrap(sb):
    res = _execute_with_retry(
        sb.table("app_state").select("current_week").eq("id", 1)
    )
    data = res.data or []
    if not data:
        _execute_with_retry(
            sb.table("app_state").insert({"id": 1, "current_week": 1})
        )
        current_week = 1
    else:
        current_week = int(data[0]["current_week"])

    w = _execute_with_retry(
        sb.table("weeks").select("week").eq("week", current_week)
    )
    if not w.data:
        _execute_with_retry(
            sb.table("weeks").insert({
                "week": current_week,
                # PostgREST expects JSON-serializable values
                "opened_at": datetime.now(timezone.utc).isoformat()
            })
        )

    return current_week

def get_current_week(sb) -> int:
    res = _execute_with_retry(
        sb.table("app_state").select("current_week").eq("id", 1)
    )
    return int(res.data[0]["current_week"])

def advance_week_pointer(sb):
    res = _execute_with_retry(
        sb.table("app_state").select("current_week").eq("id", 1)
    )
    cur = int(res.data[0]["current_week"])
    nxt = cur + 1

    _execute_with_retry(
        sb.table("weeks").update({
            "closed_at": datetime.now(timezone.utc).isoformat()
        }).eq("week", cur)
    )

    _execute_with_retry(
        sb.table("weeks").insert({
            "week": nxt,
            "opened_at": datetime.now(timezone.utc).isoformat()
        })
    )

    _execute_with_retry(
        sb.table("app_state").update({"current_week": nxt}).eq("id", 1)
    )

    return nxt
