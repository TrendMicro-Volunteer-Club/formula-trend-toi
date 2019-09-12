from common.monotonic import monotonic

import os
import sys
import threading
from collections import OrderedDict

LOG_QUIET                   = 0
LOG_ERROR                   = 1
LOG_WARN                    = 2
LOG_INFO                    = 3
LOG_DEBUG                   = 4
LOG_LEVELS                  = {LOG_QUIET: "QUIET", LOG_ERROR: "ERROR", LOG_WARN: "WARN", LOG_INFO: "INFO", LOG_DEBUG: "DEBUG"}

LOG_AGGREGATED_MIN_COUNT    = 3
LOG_AGGREGATED_MAX_COUNT    = 1000
LOG_AGGREGATED_MAX_DURATION = 60

_cur_log_level              = LOG_DEBUG
_log_mutex                  = threading.Lock()
_log_file                   = sys.stderr
_log_file_opened            = False
_last_log_msg               = OrderedDict()
_log_aggregation_enabled    = True

def _aggregate_log(msg):
    global _log_mutex, _log_file, _log_file_opened, _last_log_msg, _log_aggregation_enabled

    if not _log_aggregation_enabled:
        output = [msg, os.linesep]
        _log_file.writelines(output)
        _log_file.flush()
        return

    with _log_mutex:
        output = []
        now    = monotonic()

        if msg in _last_log_msg:
            _last_log_msg[msg]["repeated"] += 1

            if _last_log_msg[msg]["repeated"] <= LOG_AGGREGATED_MIN_COUNT:
                output.append(msg)

                if _last_log_msg[msg]["repeated"] == LOG_AGGREGATED_MIN_COUNT:
                    output.append(" (aggregated for further repeated messages)")
            else:
                delta = now - _last_log_msg[msg]["timestamp"]

                if _last_log_msg[msg]["repeated"] < LOG_AGGREGATED_MAX_COUNT and delta < LOG_AGGREGATED_MAX_DURATION:
                    return

                output.append(msg)
                output.append(" (repeated %d time(s) in last " % (_last_log_msg[msg]["repeated"]))
                if delta > 60:
                    output.append("%d minute(s))" % (int(delta) // 60))
                else:
                    output.append("%d second(s))" % (int(delta)))

                del _last_log_msg[msg]
        else:
            _last_log_msg[msg] = {"timestamp": now, "repeated": 1}
            output.append(msg)

        output.append(os.linesep)
        _log_file.writelines(output)
        _log_file.flush()

        for msg, attrs in list(_last_log_msg.items()):
            if now - attrs["timestamp"] >= LOG_AGGREGATED_MAX_DURATION:
                del _last_log_msg[msg]


def setlogaggr(enabled):
    global _log_aggregation_enabled
    if type(enabled) is str:
        enabled = True if enabled.lower() == "true" else False
    else:
        enabled = bool(enabled)

    _log_aggregation_enabled = enabled


def getloglevel():
        return _cur_log_level


def setloglevel(level):
    global _cur_log_level

    mapping = {
        "QUIET"    : LOG_QUIET,
        "LOG_QUIET": LOG_QUIET,
        "ERROR"    : LOG_ERROR,
        "LOG_ERROR": LOG_ERROR,
        "WARN"     : LOG_WARN,
        "LOG_WARN" : LOG_WARN,
        "INFO"     : LOG_INFO,
        "LOG_INFO" : LOG_INFO,
        "DEBUG"    : LOG_DEBUG,
        "LOG_DEBUG": LOG_DEBUG,
    }
    if level in (LOG_QUIET, LOG_ERROR, LOG_WARN, LOG_INFO, LOG_DEBUG):
        _cur_log_level = level
    elif level.upper() in mapping:
        _cur_log_level = mapping[level.upper()]


def setlogfile(f):
    _last_log_file   = None
    _last_log_opened = False

    try:
        with _log_mutex:
            if not f:
                _last_log_file   = _log_file
                _last_log_opened = _log_file_opened
                _log_file        = sys.stderr
                _log_file_opened = False
                return True

            if isinstance(f, file):
                _last_log_file   = _log_file
                _last_log_opened = _log_file_opened
                _log_file        = f
                _log_file_opened = False
                return True

            if type(f) is str:
                f = open(f, "a")

                if f:
                    _last_log_file   = _log_file
                    _last_log_opened = _log_file_opened
                    _log_file        = f
                    _log_file_opened = True
                    return True

            return False

    finally:
        if _last_log_file and _last_log_opened:
            try:
                _last_log_file.close()
            except:
                pass


def logit(level, fmt, *arg):
    if level <= _cur_log_level:
        _aggregate_log("[%s] %s" % (LOG_LEVELS[level], (fmt % arg)))

def logexc(level, fmt, *arg):
    if level <= _cur_log_level:
        import traceback
        exc_msg = traceback.format_exc()
        _aggregate_log("[%s] %s - %s" % (LOG_LEVELS[level], (fmt % arg), exc_msg))

def error(fmt, *arg):
    logit(LOG_ERROR, fmt, *arg)

def error_exc(fmt, *arg):
    logexc(LOG_ERROR, fmt, *arg)

def warn(fmt, *arg):
    logit(LOG_WARN, fmt, *arg)

def warn_exc(fmt, *arg):
    logexc(LOG_WARN, fmt, *arg)

def info(fmt, *arg):
    logit(LOG_INFO, fmt, *arg)

def info_exc(fmt, *arg):
    logexc(LOG_INFO, fmt, *arg)

def debug(fmt, *arg):
    logit(LOG_DEBUG, fmt, *arg)

def debug_exc(fmt, *arg):
    logexc(LOG_DEBUG, fmt, *arg)

_max_dash_length = 35
_self_checking   = False

def CHECK_PASSED(msg):
    global _self_checking
    if _self_checking:
        print("Checking %s%s[PASS]" % (msg, "." * max(_max_dash_length - len(msg), 0)))
        sys.stdout.flush()

def CHECK_FAILED(msg):
    global _self_checking
    if _self_checking:
        print("Checking %s%s[FAIL]" % (msg, "." * max(_max_dash_length - len(msg), 0)))
        sys.stdout.flush()

def set_self_check(flag):
    global _self_checking
    _self_checking = flag

