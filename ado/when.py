import datetime


def ts(s):
    """ADO's timestamps (any number of fraction digits, Z) as aware datetimes."""
    if not s:
        return None
    head, _, frac = s.rstrip("Z").partition(".")
    return datetime.datetime.fromisoformat(f"{head}.{(frac + '000000')[:6]}+00:00")


def ago(t):
    if not t:
        return ""
    s = int((datetime.datetime.now(datetime.timezone.utc) - t).total_seconds())
    return f"{s // 60}m" if s < 3600 else f"{s // 3600}t" if s < 86400 else f"{s // 86400}d"
