import botconfig
import time

def logger(file, write=True, display=True):
    def log(*output, write=write, display=display):
        output = " ".join([str(x) for x in output])
        if botconfig.DEBUG_MODE:
            write = True
        if botconfig.DEBUG_MODE or botconfig.VERBOSE_MODE:
            display = True
        timestamp = time.strftime("[%Y-%m-%d] (%H:%M:%S) %z ").upper()
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
