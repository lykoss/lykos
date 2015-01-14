import botconfig
import datetime
import time

def get_timestamp():
    """Returns a timestamp with timezone + offset from UTC."""
    if botconfig.USE_UTC:
        tmf = datetime.datetime.utcnow().strftime(botconfig.TIMESTAMP_FORMAT)
        if tmf[-1] != " ":
            tmf += " "
        return tmf.format(tzname="UTC", tzoffset="+0000")
    tmf = time.strftime(botconfig.TIMESTAMP_FORMAT)
    if tmf[-1] != " ":
        tmf += " "
    tz = time.strftime("%Z")
    utctime = datetime.datetime.utcnow().strftime("%H")
    nowtime = datetime.datetime.now().strftime("%H")
    offset = "-" if int(utctime) > int(nowtime) else "+"
    offset += str(time.timezone // 36).zfill(4)
    return tmf.format(tzname=tz, tzoffset=offset).upper()

def logger(file, write=True, display=True):
    if file is not None:
        open(file, "a").close() # create the file if it doesn't exist
    def log(*output, write=write, display=display):
        output = " ".join([str(x) for x in output]).replace("\u0002", "").replace("\x02", "") # remove bold
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
