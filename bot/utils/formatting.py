def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = (
        (f"{str(days)}d, " if days else "")
        + (f"{str(hours)}hr, " if hours else "")
        + (f"{str(minutes)}min, " if minutes else "")
        + (f"{str(seconds)}s, " if seconds else "")
    )
    return tmp[:-2]


def humanbytes(size):
    if not size:
        return "0 B"
    power = 2**10
    n = 0
    dic = {0: " ", 1: "Ki", 2: "Mi", 3: "Gi", 4: "Ti"}
    while size > power:
        size /= power
        n += 1
    return f"{str(round(size, 2))} {dic[n]}B"


def parse_duration(duration: str) -> int:
    duration = duration.lower()
    if duration.endswith("d"):
        return int(duration[:-1]) * 86400
    if duration.endswith("w"):
        return int(duration[:-1]) * 604800
    if duration.endswith("m"):
        return int(duration[:-1]) * 2592000
    if duration.endswith("y"):
        return int(duration[:-1]) * 31536000
    if duration.endswith("h"):
        return int(duration[:-1]) * 3600
    return int(duration)