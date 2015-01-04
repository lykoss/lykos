import botconfig
import datetime
import time

def get_timestamp():
    """Returns a timestamp with timezone + offset from UTC."""
    if botconfig.USE_UTC:
        return datetime.datetime.utcnow().strftime("[%Y-%m-%d] (%H:%M:%S) UTC +0000 ")
    utctime = datetime.datetime.utcnow().strftime("%H")
    nowtime = datetime.datetime.now().strftime("%H")
    offset = "+" if int(utctime) > int(nowtime) else "-"
    tz = str(time.timezone // 36)
    if len(tz) == 3:
        tz = "0" + tz
    return time.strftime("[%Y-%m-%d] (%H:%M:%S) %Z {0}{1} ").upper().format(offset, tz)

def logger(file, write=True, display=True):
    def log(*output, write=write, display=display):
        output = " ".join([str(x) for x in output])
        if botconfig.DEBUG_MODE:
            write = True
        if botconfig.DEBUG_MODE or botconfig.VERBOSE_MODE:
            display = True
        timestamp = get_timestamp()
        if display:
            print(timestamp + output)
        if write and file is not None:
            with open(file, "a") as f:
                f.seek(0, 2)
                f.write(timestamp + output + "\n")

    return log

stream_handler = logger(None)

def stream(output, level="normal"):
    if botconfig.VERBOSE_MODE or botconfig.DEBUG_MODE:
        stream_handler(output)
    elif level == "warning":
        stream_handler(output)
