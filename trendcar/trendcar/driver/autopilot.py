from common.logging   import *
from common           import config
from common.utils     import *
from car.control      import Control

from collections      import OrderedDict
from datetime         import datetime

import sys
import cv2
import threading
import functools


class AutoPilot(object):
    RESULT_NA                 = 0
    RESULT_TIMEDOUT           = 1
    RESULT_ACCEPTED           = 2

    PRIORITY_HIGH             = Control.DASHBOARD_PRIORITY_HIGH
    PRIORITY_NORMAL           = Control.DASHBOARD_PRIORITY_NORMAL
    PRIORITY_LOW              = Control.DASHBOARD_PRIORITY_LOW

    STATE_INIT                = 0
    STATE_STARTING            = 1
    STATE_STARTED             = 2
    STATE_STOPPING            = 3
    STATE_STOPPED             = 4

    DEF_RESPONSE_TIMEOUT      = 0.75
    _response_timeout         = DEF_RESPONSE_TIMEOUT

    DEF_MAX_ACTIVATION        = 320
    DEF_MIN_STARTING_STRAIGHT = 0.5
    DEF_STARTING_STRAIGHT_PWM = 1.0
    DEF_CAMERA_LAG_TOLERANCE  = 1.0

    _DEF_JPEG_QUALITY_LEVEL   = 80  # JPEG quality level: 0 - 100
    _jpeg_quality_level       = _DEF_JPEG_QUALITY_LEVEL

    _mutex                    = threading.Lock()
    _event                    = threading.Condition(_mutex)
    _thread                   = None
    _state                    = STATE_INIT
    _control                  = None
    _pilot_registry           = OrderedDict()
    _pilot_list               = []
    _remote_control_enabled   = False
    _autodrive_started        = False
    _autodrive_timestamp      = None
    _recording                = False


    @staticmethod
    def start(control = None):
        with AutoPilot._mutex:
            while AutoPilot._state in (AutoPilot.STATE_STARTING, AutoPilot.STATE_STOPPING):
                AutoPilot._event.wait()

            if AutoPilot._state == AutoPilot.STATE_STARTED:
                return True

            if AutoPilot._state in (AutoPilot.STATE_STOPPED, AutoPilot.STATE_INIT):
                AutoPilot._state = AutoPilot.STATE_STARTING
                AutoPilot._event.notify_all()

        try:
            if control is not None:
                AutoPilot.attach_control(control)

            AutoPilot._thread  = threading.Thread(target = AutoPilot.serve, name = "AutoPilot")
            AutoPilot._thread.start()
        except:
            error_exc("Unable to start AutoPilot thread")

            if control is not None:
                AutoPilot.detach_control()

            with AutoPilot._mutex:
                AutoPilot._state = AutoPilot.STATE_STOPPED
                AutoPilot._event.notify_all()

            return False

        with AutoPilot._mutex:
            while AutoPilot._state == AutoPilot.STATE_STARTING:
                AutoPilot._event.wait()
            started = AutoPilot._state == AutoPilot.STATE_STARTED

        if not started and control is not None:
            AutoPilot.detach_control()

        return started


    @staticmethod
    def stop():
        with AutoPilot._mutex:
            while AutoPilot._state in (AutoPilot.STATE_STARTING, AutoPilot.STATE_STOPPING):
                AutoPilot._event.wait()

            if AutoPilot._state in (AutoPilot.STATE_STOPPED, AutoPilot.STATE_INIT):
                return True

            AutoPilot._state = AutoPilot.STATE_STOPPING
            AutoPilot._event.notify_all()

        with AutoPilot._mutex:
            while AutoPilot._state == AutoPilot.STATE_STOPPING:
                AutoPilot._event.wait()

            stopped = AutoPilot._state == AutoPilot.STATE_STOPPED

        if stopped and AutoPilot._thread:
            AutoPilot._thread.join()
            AutoPilot._thread = None

        AutoPilot.detach_control()
        return stopped


    @staticmethod
    def attach_control(control):
        AutoPilot.detach_control()
        AutoPilot._control = control
        AutoPilot._control.register_dashboard_observer(AutoPilot._on_observe_dashboard)
        return True


    @staticmethod
    def detach_control():
        if AutoPilot._control is not None:
            AutoPilot._control.unregister_dashboard_observer(AutoPilot._on_observe_dashboard)
            AutoPilot._control = None
            return True
        return False


    @staticmethod
    def register(pilot_class):
        AutoPilot._pilot_registry[pilot_class.__name__] = pilot_class
        return pilot_class


    @staticmethod
    def priority(_priority):
        if type(_priority) is not int or _priority < AutoPilot.PRIORITY_LOW or _priority > AutoPilot.PRIORITY_HIGH:
            raise ValueError("AutoPilot.priority: Invalid priority value %s" % repr(_priority))

        def priority_setter(func):
            func._priority = _priority
            return func

        return priority_setter


    @staticmethod
    def priority_high(func):
        func._priority = AutoPilot.PRIORITY_HIGH
        return func


    @staticmethod
    def priority_normal(func):
        func._priority = AutoPilot.PRIORITY_NORMAL
        return func


    @staticmethod
    def priority_low(func):
        func._priority = AutoPilot.PRIORITY_LOW
        return func


    @staticmethod
    def _pilot_thread(pilot_context):
        set_thread_name(pilot_context["thread"].getName())
        try:
            with pilot_context["mutex"]:
                pilot_context["running"       ] = True
                pilot_context["command"       ] = None
                pilot_context["elapsed"       ] = None
                pilot_context["last_timestamp"] = None
                pilot_context["event"].notify_all()

            while AutoPilot._state == AutoPilot.STATE_STARTED and pilot_context["running"]:
                try:
                    with pilot_context["mutex"]:
                        if pilot_context["last_timestamp"] == AutoPilot._last_timestamp:
                            pilot_context["event"].wait()
                            continue
                        pilot_context["last_timestamp"] = AutoPilot._last_timestamp
                        pilot_context["command"       ] = None
                        pilot_context["elapsed"       ] = None

                    start = monotonic()
                    command = pilot_context["pilot"].on_inquiry_drive(AutoPilot._dashboard, pilot_context.get("last_result", AutoPilot.RESULT_NA))
                    elapsed = monotonic() - start

                    with pilot_context["mutex"]:
                        pilot_context["command"] = command
                        pilot_context["elapsed"] = elapsed
                        pilot_context["event"  ].notify_all()
                except:
                    error_exc("AutoPilot: Exception occurred while executing %s.on_inquiry_drive()", pilot_context["pilot"].__class__.__name__)
        finally:
            with pilot_context["mutex"]:
                pilot_context["running"] = False
                pilot_context["event"].notify_all()


    @staticmethod
    def _init_pilot_list():
        for name, pilot_class in AutoPilot._pilot_registry.items():
            try:
                pilot = pilot_class()
                pilot_context = {"pilot": pilot}

                pilot_context["thread" ] = threading.Thread(target = AutoPilot._pilot_thread, args = (pilot_context,), name = "-%s" % name)
                pilot_context["mutex"  ] = threading.Lock()
                pilot_context["event"  ] = threading.Condition(pilot_context["mutex"])
                pilot_context["running"] = False

                if "on_inquiry_drive" in vars(pilot.__class__):
                    func = vars(pilot.__class__).get("on_inquiry_drive")
                    inquiry_drive_priority = vars(func).get("_priority", AutoPilot.PRIORITY_NORMAL)
                else:
                    inquiry_drive_priority = AutoPilot.PRIORITY_NORMAL

                pilot._priority = (-inquiry_drive_priority, len(AutoPilot._pilot_list))

                pilot_context["thread" ].setDaemon(True)
                pilot_context["thread" ].start()
                AutoPilot._pilot_list.append(pilot_context)
                info("AutoPilot: loaded %s", name)
            except:
                error_exc("Exception occurred while creating instance of %s", name)

        _cmp_ = lambda a, b: (int(a > b) - int(a < b))
        AutoPilot._pilot_list.sort(key = functools.cmp_to_key(lambda x, y: _cmp_(x["pilot"]._priority, y["pilot"]._priority)))
        info("AutoPilot: Sorted by priority - %s", str([p["pilot"].__class__.__name__ for p in AutoPilot._pilot_list]))

        # ensure all pilot threads are started
        for pilot_context in AutoPilot._pilot_list:
            with pilot_context["mutex"]:
                if not pilot_context["running"]:
                    pilot_context["event"].wait()

        for pilot_context in AutoPilot._pilot_list:
            pilot       = pilot_context["pilot"]
            pilot_class = pilot.__class__
            if "on_edit_dashboard" in vars(pilot_class):
                edit_dashboard_priority = vars(pilot_class.on_edit_dashboard).get("_priority", AutoPilot.PRIORITY_NORMAL)
                AutoPilot._control.register_dashboard_editor(pilot.on_edit_dashboard, priority = edit_dashboard_priority)

        return True


    @staticmethod
    def _uninit_pilot_list():
        for pilot_context in reversed(AutoPilot._pilot_list):
            pilot       = pilot_context["pilot"]
            pilot_class = pilot.__class__

            try:
                if "on_edit_dashboard" in vars(pilot_class):
                    AutoPilot._control.unregister_dashboard_editor(pilot.on_edit_dashboard)

                with pilot_context["mutex"]:
                    start = monotonic()
                    delta = 0
                    while pilot_context["running"] and delta < AutoPilot._response_timeout * 5:
                        pilot_context["event"].notify_all()
                        pilot_context["event"].wait(AutoPilot._response_timeout * 5 - delta)
                        delta = monotonic() - start

                    if pilot_context["running"]:
                        warn("AutoPilot: Skipped unloading %s. The on_inquiry_drive method seemed to be blocked.", pilot_class.__name__)
                    else:
                        info("AutoPilot: Unloaded %s", pilot_class.__name__)
            except:
                error_exc("AutoPilot: Exception occurred while deleting instance of %s", pilot_class.__name__)

        AutoPilot._pilot_list = []


    @staticmethod
    def start_autodrive():
        AutoPilot._autodrive_started   = True
        AutoPilot._autodrive_timestamp = monotonic()


    @staticmethod
    def stop_autodrive():
        AutoPilot._autodrive_started   = False
        AutoPilot._autodrive_timestamp = None


    @staticmethod
    def get_autodrive_started():
        if AutoPilot.get_remote_control_enabled():
            return False
        return AutoPilot._autodrive_started


    @staticmethod
    def get_autodrive_elapsed():
        timestamp = AutoPilot._autodrive_timestamp
        if timestamp is None:
            return 0.0
        return monotonic() - timestamp


    @staticmethod
    def enable_remote_control():
        AutoPilot._remote_control_enabled = True
        AutoPilot.stop_autodrive()


    @staticmethod
    def disable_remote_control():
        AutoPilot._remote_control_enabled = False


    @staticmethod
    def get_remote_control_enabled():
        return AutoPilot._remote_control_enabled


    @staticmethod
    def start_recording():
        AutoPilot._recording = True


    @staticmethod
    def stop_recording():
        AutoPilot._recording = False


    @staticmethod
    def is_recording():
        return AutoPilot._recording


    @staticmethod
    def _snapshot_frame(frame, steering = None, throttle = None, pwms = None):
        filename = "recording-%s-auto" % (datetime.now().strftime("%Y%m%d-%H%M%S.%f"))

        if pwms is not None and type(pwms) in (tuple, list) and len(pwms) == 4:
            suffix = ",fl={},rl={},fr={},rr={}".format(*("%+06.3f" % (pwm) for pwm in pwms))
        elif steering is not None and throttle is not None:
            suffix = ",s=%s,t=%s" % ("%+06.2f" % (steering), "%+06.3f" % (throttle))
        else:
            suffix = ""

        jpegfile = os.path.join(AutoPilot._recording_folder, "%s%s.jpg" % (filename, suffix))

        try:
            if not os.path.exists(AutoPilot._recording_folder):
                os.makedirs(AutoPilot._recording_folder)

            if os.path.isdir(AutoPilot._recording_folder):
                ret, frame = cv2.imencode('.jpg', frame , [cv2.IMWRITE_JPEG_QUALITY, AutoPilot._jpeg_quality_level])
                if ret:
                    with open(jpegfile, "wb") as f:
                        f.write(frame)
                    return True

            warn("Unable to record frame. %s was not a valid folder", AutoPilot._recording_folder)
        except:
            warn_exc("Exception occurred. Unable to record frame to %s.", jpegfile) 

        return False


    @staticmethod
    def vibrate(count):
        import time

        AutoPilot._control.drive(0.0, 0.0)

        for i in range(count):
            AutoPilot._control.vibrate(3, 0.01)
            time.sleep(0.2)


    @staticmethod
    def _on_observe_dashboard(dashboard):
        with AutoPilot._mutex:
            AutoPilot._dashboard = dashboard

            ready_to_go = AutoPilot._dashboard.get("ready_to_go", None)

            if ready_to_go is not None:
                if ready_to_go:
                    AutoPilot.start_autodrive()
                else:
                    AutoPilot.stop_autodrive()

            AutoPilot._dashboard["started"] = AutoPilot._autodrive_started
            AutoPilot._event.notify_all()
        return False


    @staticmethod
    def serve():
        set_thread_name("AutoPilot.serve")
        AutoPilot._recording_folder   = config.get     ("DEFAULT"  , "recording_folder"             , None)
        AutoPilot._response_timeout   = config.getfloat("AUTOPILOT", "response_timeout"             , AutoPilot.DEF_RESPONSE_TIMEOUT     )
        max_activation_seconds        = config.getfloat("AUTOPILOT", "max_activation_seconds"       , AutoPilot.DEF_MAX_ACTIVATION       )
        min_starting_straight_seconds = config.getfloat("AUTOPILOT", "min_starting_straight_seconds", AutoPilot.DEF_MIN_STARTING_STRAIGHT)
        starting_straight_throttle    = config.getfloat("AUTOPILOT", "starting_straight_throttle"   , AutoPilot.DEF_STARTING_STRAIGHT_PWM)
        camera_lag_tolerance_seconds  = config.getfloat("AUTOPILOT", "camera_lag_tolerance_seconds" , AutoPilot.DEF_CAMERA_LAG_TOLERANCE )
        dashboard_max_renew_interval  = 0

        if camera_lag_tolerance_seconds > 0 and dashboard_max_renew_interval > camera_lag_tolerance_seconds:
            dashboard_max_renew_interval = camera_lag_tolerance_seconds

        if min_starting_straight_seconds > 0 and dashboard_max_renew_interval > min_starting_straight_seconds:
            dashboard_max_renew_interval = min_starting_straight_seconds

        if max_activation_seconds > 0 and dashboard_max_renew_interval > max_activation_seconds:
            dashboard_max_renew_interval = max_activation_seconds

        try:
            with AutoPilot._mutex:
                AutoPilot._state = AutoPilot.STATE_STARTED
                AutoPilot._event.notify_all()

            info("AutoPilot: started")

            AutoPilot._dashboard      = {}
            AutoPilot._last_timestamp = monotonic()
            AutoPilot._pilot_started  = None

            AutoPilot._init_pilot_list()

            with AutoPilot._mutex:
                while AutoPilot._state == AutoPilot.STATE_STARTED:
                    try:
                        if max_activation_seconds > 0 and AutoPilot.get_autodrive_elapsed() > max_activation_seconds:
                            info("AutoPilot: Time's up! Autodriving deactivated automatically after %0.4f seconds.", max_activation_seconds)
                            AutoPilot.stop_autodrive()

                        if AutoPilot._dashboard.get("timestamp", AutoPilot._last_timestamp) == AutoPilot._last_timestamp:
                            if dashboard_max_renew_interval > 0:
                                if monotonic() - AutoPilot._last_timestamp > camera_lag_tolerance_seconds:
                                    debug("AutoPilot: Pause driving due to the camera lag exceeding %0.4f seconds", camera_lag_tolerance_seconds)
                                    AutoPilot._control.drive(0.0, 0.0)

                                AutoPilot._event.wait(timeout = dashboard_max_interval)
                            else:
                                AutoPilot._event.wait()

                            continue

                        dashboard = AutoPilot._dashboard
                        AutoPilot._last_timestamp = dashboard["timestamp"]

                        try:
                            AutoPilot._event.release()

                            has_running_pilots = False

                            for pilot_context in AutoPilot._pilot_list:
                                if AutoPilot._state != AutoPilot.STATE_STARTED:
                                    break
                                if not pilot_context["running"]:
                                    continue

                                try:
                                    with pilot_context["mutex"]:
                                        if pilot_context["last_timestamp"] != AutoPilot._last_timestamp:
                                            pilot_context["event"].notify_all()

                                        start   = monotonic()
                                        elapsed = 0
                                        while pilot_context["running"] and elapsed < AutoPilot._response_timeout:
                                            if pilot_context["last_timestamp"] == AutoPilot._last_timestamp and pilot_context["command"] is not None:
                                                break
                                            if pilot_context["elapsed"] is not None:
                                                break
                                            pilot_context["event"].wait(AutoPilot._response_timeout - elapsed)
                                            elapsed = monotonic() - start

                                        if not pilot_context["running"]:
                                            debug("AutoPilot: %s was not running", pilot_context["pilot"].__class__.__name__)
                                            continue

                                        if elapsed >= AutoPilot._response_timeout:
                                            debug("AutoPilot: %s.on_inquiry_drive() timed out", pilot_context["pilot"].__class__.__name__)
                                            continue

                                        if pilot_context["command"] is None:
                                            debug("AutoPilot: %s.on_inquiry_drive() returned empty command in %0.3f seconds", pilot_context["pilot"].__class__.__name__, pilot_context["elapsed"])
                                            continue

                                        has_running_pilots = True
                                        command = pilot_context["command"]

                                        if pilot_context["elapsed"] is not None:
                                            elapsed = pilot_context["elapsed"] 


                                    def _during_starting_straight_period():
                                        if AutoPilot.get_autodrive_started():
                                            if AutoPilot._pilot_started is None:
                                                AutoPilot._pilot_started = monotonic()

                                            if monotonic() - AutoPilot._pilot_started < min_starting_straight_seconds:
                                                return True
                                        else:
                                            AutoPilot._pilot_started = None

                                        return False


                                    def _get_by_pwm_keyword(key):
                                        for k in command.keys():
                                            if (k.lower() == key.lower()) or \
                                               (k.lower() + "_pwm" == key.lower()) or \
                                               (k.replace("-", "_").lower() == key.lower()) or \
                                               (k.replace("-", "_").lower() + "_pwm" == key.lower()):
                                                return float(command[k])

                                        return None

                                    front_left_pwm  = _get_by_pwm_keyword("front_left_pwm" )
                                    rear_left_pwm   = _get_by_pwm_keyword("rear_left_pwm"  )
                                    front_right_pwm = _get_by_pwm_keyword("front_right_pwm")
                                    rear_right_pwm  = _get_by_pwm_keyword("rear_right_pwm" )
                                    duration        = float(command["duration"]) if "duration" in command else 0.0
                                    override        = bool(command["override"])  if "override" in command else False

                                    if all(map(lambda x: x is not None, (front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm))):
                                        debug("AutoPilot: %s.on_inquiry_drive() returned (front_left_pwm = %0.4f, rear_left_pwm = %0.4f, front_right_pwm = %0.4f, rear_right_pwm = %0.4f) in %0.3f seconds", pilot_context["pilot"].__class__.__name__, front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm, elapsed)

                                        if _during_starting_straight_period():
                                            if starting_straight_throttle > 0:
                                                pwm = starting_straight_throttle
                                            else:
                                                pwm = max(front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm)

                                            front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm = pwm, pwm, pwm, pwm
                                            debug("AutoPilot: Enforced to go straight during the starting period of %0.4f seconds (4WD PWM = %0.4f)" % (min_starting_straight_seconds, pwm))

                                        AutoPilot._control.drive_by_pwms(front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm, duration = duration, override = override)

                                        if AutoPilot.is_recording():
                                            frame = dashboard.get("frame", None)
                                            if frame is not None:
                                                AutoPilot._snapshot_frame(frame, pwms = (front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm))

                                        break

                                    steering = command.get("steering", None)
                                    throttle = command.get("throttle", None)
                                    flipped  = bool(command["flipped"]) if "flipped" in command else bool(dashboard["flipped"]) if "flipped" in dashboard else False

                                    if steering is None:
                                        if any(map(lambda x: x is not None, (front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm))):
                                            debug("AutoPilot: %s.on_inquiry_drive() returned the command without specifying full pwms in %0.3f seconds", pilot_context["pilot"].__class__.__name__, elapsed)
                                        else:
                                            debug("AutoPilot: %s.on_inquiry_drive() returned the command without specifying steering in %0.3f seconds", pilot_context["pilot"].__class__.__name__, elapsed)
                                        continue

                                    if throttle is None:
                                        debug("AutoPilot: %s.on_inquiry_drive() returned the command without specifying throttle in %0.3f seconds", pilot_context["pilot"].__class__.__name__, elapsed)
                                        continue

                                    debug("AutoPilot: %s.on_inquiry_drive() returned (steering = %0.2f, throttle = %0.4f) in %0.3f seconds", pilot_context["pilot"].__class__.__name__, steering, throttle, elapsed)

                                    if _during_starting_straight_period():
                                        steering = 0.0
                                        if starting_straight_throttle > 0:
                                            throttle = starting_straight_throttle

                                        debug("AutoPilot: Enforced to go straight during the starting period of %0.4f seconds (throttle = %0.4f)" % (min_starting_straight_seconds, throttle))

                                    AutoPilot._control.drive(steering, throttle, duration = duration, flipped = flipped, override = override)

                                    if AutoPilot.is_recording():
                                        frame = dashboard.get("frame", None)
                                        if frame is not None:
                                            AutoPilot._snapshot_frame(frame, steering = steering, throttle = throttle)

                                    break
                                except:
                                    error_exc("Exception occurred while inquirying drive command from %s", pilot_context["pilot"].__class__.__name__)

                            if not has_running_pilots:
                                debug("AutoPilot: Stop driving due to no running pilots")
                                AutoPilot._control.drive(0.0, 0.0)

                                if AutoPilot.is_recording():
                                    frame = dashboard.get("frame", None)
                                    if frame is not None:
                                        AutoPilot._snapshot_frame(frame)

                        finally:
                            AutoPilot._event.acquire()

                    except KeyboardInterrupt:
                        break
                    except:
                        error_exc("AutoPilot: Error occurred")

        finally:
            AutoPilot._uninit_pilot_list()

            with AutoPilot._mutex:
                AutoPilot._state = AutoPilot.STATE_STOPPED
                AutoPilot._event.notify_all()
                info("AutoPilot: stopped")


    #def on_edit_dashboard(self, dashboard):
    #    return False

    def on_inquiry_drive(self, dashboard, last_result):
        return None


if __name__ == "__main__":
    with Control.auto_detect() as control:
        if control is None:
            error("No car controls could be initiated")
            sys.exit(1)

        AutoPilot.attach_control(control)

        try:
            AutoPilot.serve()
        finally:
            AutoPilot.detach_control()

    sys.exit(0)

