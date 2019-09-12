from common.logging import *

import os
import cv2
import time
import threading

COMPATIBLE_TRANSITION_LIST = (
    # old submodule & name              new name for opencv 3
    ("cv", "CV_CAP_PROP_FRAME_WIDTH" , "CAP_PROP_FRAME_WIDTH" ),
    ("cv", "CV_CAP_PROP_FRAME_HEIGHT", "CAP_PROP_FRAME_HEIGHT"),
    ("cv", "CV_CAP_PROP_FPS"         , "CAP_PROP_FPS"         ),
    (None, "CV_AA"                   , "LINE_AA"              ),
    (None, "IMREAD_COLOR"            , "CV_LOAD_IMAGE_COLOR"  ),
)

info("Using OpenCV %s", cv2.__version__)

for old_submodule, old_key, new_key in COMPATIBLE_TRANSITION_LIST:
    try:
        if old_submodule is None:
            old_value = eval("cv2.%s" % old_key)
        elif old_submodule in cv2.__dict__:
            old_value = eval("cv2.%s.%s" % (old_submodule, old_key))
        else:
            continue
    except:
        old_value = None

    try:
        new_value = eval("cv2.%s" % new_key)
    except:
        new_value = None

    if old_value is None:
        if new_value is None:
            warn("cv2compat: both %s and %s were not found", old_key, new_key)
            continue
        try:
            if old_submodule is None:
                exec("cv2.%s=%s" % (old_key, repr(new_value)))
            else:
                exec("cv2.%s.%s=%s" % (old_submodule, old_key, repr(new_value)))
        except:
            warn_exc("cv2compat: Failed to assign %s = %s", old_key, new_key)
        continue

    if new_value is None:
        try:
            exec("cv2.%s=%s" % (new_key, repr(old_value)))
        except:
            warn_exc("cv2compat: Failed to assign %s = %s", new_key, repr(old_value))
        continue

_window_mutex       = threading.Lock()
_window_added_event = threading.Condition(_window_mutex)
_window_list        = set()
_window_displayed   = set()

# window should be opened/created by the main thread
def display_window():
    if "DISPLAY" in os.environ or sys.platform in ['darwin']:
        global _window_mutex, _window_added_event, _window_list, _window_displayed

        with _window_mutex:
            to_display = _window_list - _window_displayed

            if to_display:
                try:
                    for window_name in to_display:
                        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                        cv2.waitKey(1)
                except:
                    pass

                _window_displayed = _window_displayed.union(to_display)
                _window_added_event.notify_all()

        cv2.waitKey(100)
    else:
        time.sleep(1)


def show_image(window_name, image):
    if "DISPLAY" in os.environ or sys.platform in ['darwin']:
        global _window_mutex, _window_added_event, _window_list, _window_displayed

        with _window_mutex:
            if window_name not in _window_list:
                _window_list.add(window_name)

                while window_name not in _window_displayed:
                    _window_added_event.wait()

        cv2.imshow(window_name, image)

