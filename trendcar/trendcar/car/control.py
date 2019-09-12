from common.stuff     import *
from car              import model

from collections      import OrderedDict
import threading


class Control(object):
    """
    """
    STATE_INIT                    = 0
    STATE_STARTING                = 1
    STATE_STARTED                 = 2
    STATE_STOPPING                = 3
    STATE_STOPPED                 = 4

    REQUEST_CREATED               = "created"
    REQUEST_UPDATED               = "updated"
    REQUEST_DURATION              = "duration"
    REQUEST_COUNT                 = "count"
    REQUEST_COMMAND               = "command"
    REQUEST_COMMAND_DRIVE         = "drive"
    REQUEST_COMMAND_DRIVE_BY_PWMS = "drive_by_pwms"
    REQUEST_PARAMS                = "params"

    DASHBOARD_PRIORITY_HIGH       = 9
    DASHBOARD_PRIORITY_NORMAL     = 5
    DASHBOARD_PRIORITY_LOW        = 1

    MAX_QUEUED_DRIVE_COMMANDS     = 1

    @staticmethod
    def auto_detect(dummyResult = True, quiet = False):
        control = None
        for model_name in model.get_model_names():
            try:
                debug("Trying %s", model_name)
                control = Control(model_name = model_name)
                if control.begin(is_detecting = True, quiet = quiet):
                    break
                control.end(quiet = quiet)
                control = None
            except:
                error_exc("Unexpected error occurred while trying %s", model_name)

            control = None

        if dummyResult and control is None:
            control = Control(model_name = "NullModel")

        return control


    @staticmethod
    def launch(model_name, dummyResult = True, quiet = False, ignore_platform_check = False):
        control = None

        try:
            debug("Launching %s", model_name)
            control = Control(model_name = model_name)
            if control.begin(quiet = quiet, ignore_platform_check = ignore_platform_check):
                return control

            control.end(quiet = quiet)
        except:
            error_exc("Unexpected error occurred while launching %s", model_name)

        control = None

        if dummyResult:
            control = Control(model_name = "NullModel")

        return control


    def __init__(self, model_name = None):
        self._model                       = model.get_model(model_name)

        self._state                       = self.STATE_INIT
        self._state_mutex                 = threading.Lock()
        self._state_event                 = threading.Condition(self._state_mutex)

        self._dashboard_running           = False
        self._dashboard_thread            = None
        self._dashboard_mutex             = threading.Lock()
        self._dashboard_event             = threading.Condition(self._dashboard_mutex)
        self._dashboard_editors           = {}
        self._dashboard_editors_changed   = False
        self._dashboard_editor_list       = []
        self._dashboard_observers         = {}
        self._dashboard_observers_changed = False
        self._dashboard_observer_list     = {}

        self._dispatcher_running          = False
        self._dispatcher_thread           = None
        self._dispatcher_mutex            = threading.Lock()
        self._dispatcher_event            = threading.Condition(self._dispatcher_mutex)
        self._dispatcher_requests         = []


    def __enter__(self):
        if self.is_ready():
            return self
        return None


    def __exit__(self, t, v, tb):
        if self.is_ready():
            self.end()


    def is_running(self):
        return self._state in (self.STATE_STARTING, self.STATE_STARTED)


    def is_starting(self):
        return self._state == self.STATE_STARTING


    def is_ready(self):
        return self._state == self.STATE_STARTED


    def is_stopping(self):
        return self._state == self.STATE_STOPPING


    def is_stopped(self):
        return self._state in (self.STATE_STOPPING, self.STATE_STOPPED)


    def can_begin(self):
        return self._state in (self.STATE_INIT, self.STATE_STOPPED)


    def wait_for_states(self, state_list, timeoutSec = None):
        with self._state_mutex:
            timestamp = monotonic()
            while self._state not in state_list:
                self._state.wait(timeout = timeoutSec)

                if timeoutSec is not None and monotonic() - timestamp >= timeoutSec:
                    return self._state in state_list

        return True


    def wait_for_state_changed(self, timeoutSec = None):
        with self._state_mutex:
            timestamp = monotonic()
            orig_state = self._state

            while self._state == orig_state:
                self._state.wait(timeout = timeoutSec)

                if timeoutSec is not None and monotonic() - timestamp >= timeoutSec:
                    return orig_state != self._state

        return True


    def _update_dashboard_editor_list(self):
        if not self._dashboard_editors_changed:
            return

        self._dashboard_editor_list = []
        for i in range(self.DASHBOARD_PRIORITY_HIGH, self.DASHBOARD_PRIORITY_LOW - 1, -1):
            if i not in self._dashboard_editors:
                continue
            for editor in self._dashboard_editors[i]:
                for context_list in self._dashboard_editors[i][editor]:
                    self._dashboard_editor_list.append((editor, context_list))

        self._dashboard_editors_changed = False


    def register_dashboard_editor(self, editor, argv = None, priority = DASHBOARD_PRIORITY_NORMAL):
        if priority > self.DASHBOARD_PRIORITY_HIGH:
            priority = self.DASHBOARD_PRIORITY_HIGH
        elif priority < self.DASHBOARD_PRIORITY_LOW:
            priority = self.DASHBOARD_PRIORITY_LOW

        with self._dashboard_mutex:
            if priority not in self._dashboard_editors:
                self._dashboard_editors[priority] = OrderedDict()

            if editor not in self._dashboard_editors[priority]:
                self._dashboard_editors[priority][editor] = OrderedDict()

            self._dashboard_editors[priority][editor][argv] = True
            self._dashboard_editors_changed = True
            self._dashboard_event.notify_all()

        return True


    def unregister_dashboard_editor(self, editor, argv = None):
        removed = False

        with self._dashboard_mutex:
            for i in range(self.DASHBOARD_PRIORITY_LOW, self.DASHBOARD_PRIORITY_HIGH + 1):
                if i not in self._dashboard_editors:
                    continue
                if editor not in self._dashboard_editors[i]:
                    continue

                if argv in self._dashboard_editors[i][editor]:
                    del self._dashboard_editors[i][editor][argv]

                    if len(self._dashboard_editors[i][editor]) == 0:
                        del self._dashboard_editors[i][editor]

                    self._dashboard_editors_changed = True
                    break

            if self._dashboard_editors_changed:
                self._dashboard_event.notify_all()

        return removed


    def _update_dashboard_observer_list(self):
        if not self._dashboard_observers_changed:
            return

        self._dashboard_observer_list = []
        for i in range(self.DASHBOARD_PRIORITY_HIGH, self.DASHBOARD_PRIORITY_LOW - 1, -1):
            if i not in self._dashboard_observers:
                continue
            for observer in self._dashboard_observers[i]:
                for context_list in self._dashboard_observers[i][observer]:
                    self._dashboard_observer_list.append((observer, context_list))

        self._dashboard_observers_changed = False


    def register_dashboard_observer(self, observer, argv = None, priority = DASHBOARD_PRIORITY_NORMAL):
        if priority > self.DASHBOARD_PRIORITY_HIGH:
            priority = self.DASHBOARD_PRIORITY_HIGH
        elif priority < self.DASHBOARD_PRIORITY_LOW:
            priority = self.DASHBOARD_PRIORITY_LOW

        with self._dashboard_mutex:
            if priority not in self._dashboard_observers:
                self._dashboard_observers[priority] = OrderedDict()

            if observer not in self._dashboard_observers[priority]:
                self._dashboard_observers[priority][observer] = OrderedDict()

            self._dashboard_observers[priority][observer][argv] = True
            self._dashboard_observers_changed = True
            self._dashboard_event.notify_all()

        return True


    def unregister_dashboard_observer(self, observer, argv = None):
        removed = False

        with self._dashboard_mutex:
            for i in range(self.DASHBOARD_PRIORITY_LOW, self.DASHBOARD_PRIORITY_HIGH + 1):
                if i not in self._dashboard_observers:
                    continue
                if observer not in self._dashboard_observers[i]:
                    continue

                if argv in self._dashboard_observers[i][observer]:
                    del self._dashboard_observers[i][observer][argv]

                    if len(self._dashboard_observers[i][observer]) == 0:
                        del self._dashboard_observers[i][observer]

                    self._dashboard_observers_changed = True
                    break

            if self._dashboard_observers_changed:
                self._dashboard_event.notify_all()

        return removed


    def _dashboard_loop(self):
        set_thread_name(self._dashboard_thread.getName())

        with self._dashboard_mutex:
            self._dashboard_running = True
            self._dashboard_event.notify_all()
            info("Control: Dashboard thread started")

        sampling_interval = 1.0 / self.get_frame_rate()
        last_output_time  = monotonic()
        last_process_time = 0.0
        frame_start_time  = last_output_time
        frame_count       = 0
        frame_rate        = 0.0

        while self.is_running():
            self._update_dashboard_editor_list()
            self._update_dashboard_observer_list()

            if len(self._dashboard_editor_list) == 0 and len(self._dashboard_observer_list) == 0:
                with self._dashboard_mutex:
                    if len(self._dashboard_editors) == 0 and len(self._dashboard_observers) == 0:
                        self._dashboard_event.wait()
                        continue

            delta = monotonic() - last_output_time
            if delta < sampling_interval:
                with self._dashboard_mutex:
                    self._dashboard_event.wait(sampling_interval - delta)
                    continue

            last_output_time = monotonic()

            dashboard = {
                "timestamp"        : last_output_time,
                "last_process_time": last_process_time,
                "frame"            : self.get_snapshot(),
                "all_frames"       : self.get_all_snapshots(),
                "frame_width"      : self.get_frame_width(),
                "frame_height"     : self.get_frame_height(),
                "frame_rate"       : frame_rate if frame_rate > 0.0 else self.get_frame_rate(),
                "flipped"          : False,
                "ready_to_go"      : self.ready_to_go(),
            }

            for editor, context in self._dashboard_editor_list:
                try:
                    if context is None:
                        if editor(dashboard):
                            break
                    else:
                        if editor(dashboard, *context):
                            break
                except:
                    error_exc("Error executing dashboard editor %s", repr(editor))

            for observer, context in self._dashboard_observer_list:
                try:
                    if context is None:
                        if observer(dashboard):
                            break
                    else:
                        if observer(dashboard, *context):
                            break
                except:
                    error_exc("Error executing dashboard observer %s", repr(observer))

            last_process_time = monotonic() - last_output_time

            frame_count   += 1
            frame_end_time = monotonic()
            frame_interval = frame_end_time - frame_start_time
            if frame_interval > 1.0:
                frame_rate = frame_count / frame_interval

                if frame_interval > 10.0:
                    debug("Control: average frame rate in last 10 seconds = %0.2f fps", (frame_rate))
                    frame_count      = 0
                    frame_start_time = frame_end_time

        with self._dashboard_mutex:
            self._dashboard_running = False
            self._dashboard_event.notify_all()
            info("Control: Dashboard thread ended")


    def _dispatcher_loop(self):
        set_thread_name(self._dispatcher_thread.getName())

        with self._dispatcher_mutex:
            try:
                self._dispatcher_running = True
                self._dispatcher_event.notify_all()
                info("Control: Dispatcher thread started")

                while self.is_running():
                    if len(self._dispatcher_requests) == 0:
                        self._dispatcher_event.notify_all()
                        self._dispatcher_event.wait()
                        continue

                    request = self._dispatcher_requests.pop(0)

                    if request is None:
                        continue

                    if request[self.REQUEST_COMMAND] == self.REQUEST_COMMAND_DRIVE:
                        try:
                            self._dispatcher_mutex.release()
                            self._model.drive(*request[self.REQUEST_PARAMS])
                        finally:
                            self._dispatcher_mutex.acquire()

                    elif request[self.REQUEST_COMMAND] == self.REQUEST_COMMAND_DRIVE_BY_PWMS:
                        try:
                            self._dispatcher_mutex.release()
                            self._model.drive_by_pwms(*request[self.REQUEST_PARAMS])
                        finally:
                            self._dispatcher_mutex.acquire()

            finally:
                self._dispatcher_running = False
                self._dispatcher_event.notify_all()
                info("Control: Dispatcher thread ended")


    def wait_for_requests_done(self, timeoutSec = None):
        with self._dispatcher_mutex:
            if not self._dispatcher_running:
                return False

            timestamp = monotonic()

            while self._dispatcher_running and len(self._dispatcher_requests) > 0:
                self._dispatcher_event.wait(timeout = timeoutSec)

                if timeoutSec is not None and monotonic() - timestamp >= timeoutSec:
                    return len(self._dispatcher_requests) == 0
        return True


    def begin(self, is_detecting = False, quiet = False, ignore_platform_check = False):
        with self._state_mutex:
            if self.is_running():
                return True

            if not self.can_begin():
                if not self.is_stopping():
                    return False

                while not self.can_begin():
                    self._state_event.wait()

            self._state = self.STATE_STARTING
            self._state_event.notify_all()

        if not self._model.begin(is_detecting = is_detecting, ignore_platform_check = ignore_platform_check):
            if is_detecting:
                debug("Control: unable to init the model %s", self._model)
            else:
                error("Control: unable to init the model %s", self._model)

            with self._state_mutex:
                self._state = self.STATE_STOPPED
                self._state_event.notify_all()

            return False

        try:
            with self._dispatcher_mutex:
                if not self._dispatcher_running:
                    self._dispatcher_thread = threading.Thread(target = self._dispatcher_loop, name = "ctrl-dispatcher")
                    self._dispatcher_thread.start()

            with self._dashboard_mutex:
                if not self._dashboard_running:
                    self._dashboard_thread = threading.Thread(target = self._dashboard_loop , name = "ctrl-dashboard")
                    self._dashboard_thread.start()

            with self._dispatcher_mutex:
                while not self._dispatcher_running:
                    self._dispatcher_event.wait()

            with self._dashboard_mutex:
                while not self._dashboard_running:
                    self._dashboard_event.wait()

            with self._state_mutex:
                self._state = self.STATE_STARTED
                self._state_event.notify_all()

            if not quiet:
                self.vibrate(5, 0.03)

            return True

        except:
            error_exc("Control: unable to begin dashboard/dispatcher threads for model %s", self._model)

            with self._state_mutex:
                self._state = self.STATE_STOPPED
                self._state_event.notify_all()

        return False


    def end(self, quiet = False):
        with self._state_mutex:
            if not self.is_running():
                return True

            while self.is_starting():
                self._state_event.wait()

            if not self.is_running():
                return True

            self._state = self.STATE_STOPPING
            self._state_event.notify_all()

        with self._dispatcher_mutex:
            self._dispatcher_event.notify_all()

        with self._dashboard_mutex:
            self._dashboard_event.notify_all()

        with self._dispatcher_mutex:
            while self._dispatcher_running:
                self._dispatcher_event.wait()
            self._dispatcher_thread = None
                
        with self._dashboard_mutex:
            while self._dashboard_running:
                self._dashboard_event.wait()
            self._dashboard_thread = None

        if not quiet:
            self.vibrate(3)

        self._model.end()

        with self._state_mutex:
            self._state = self.STATE_STOPPED
            self._state_event.notify_all()

        return True


    def drive_by_pwms(self, front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm, duration = 0.0, override = False):
        with self._state_mutex:
            if not self.is_ready():
                return False

        front_left_pwm  = max(min(front_left_pwm , 1.0), -1.0)
        rear_left_pwm   = max(min(rear_left_pwm  , 1.0), -1.0)
        front_right_pwm = max(min(front_right_pwm, 1.0), -1.0)
        rear_right_pwm  = max(min(rear_right_pwm , 1.0), -1.0)
        duration        = max(min(duration, 5.0), 0.0)
        override        = (override == True)

        with self._dispatcher_mutex:
            params = (front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm, duration)

            if override:
                self._dispatcher_requests = []
            else:
                for request in reversed(self._dispatcher_requests):
                    if request[self.REQUEST_COMMAND] == self.REQUEST_COMMAND_DRIVE_BY_PWMS:
                        if request[self.REQUEST_PARAMS] == params:
                            # aggregate the repeated commands
                            request[self.REQUEST_UPDATED ]  = monotonic()
                            request[self.REQUEST_COUNT   ] += 1
                            return True
                        break

            while len(self._dispatcher_requests) >= self.MAX_QUEUED_DRIVE_COMMANDS:
                self._dispatcher_event.notify_all()
                self._dispatcher_event.wait()

                if not self.is_ready():
                    return False

            self._dispatcher_requests.append({
                self.REQUEST_CREATED: monotonic(),
                self.REQUEST_UPDATED: monotonic(),
                self.REQUEST_COUNT  : 1,
                self.REQUEST_COMMAND: self.REQUEST_COMMAND_DRIVE_BY_PWMS,
                self.REQUEST_PARAMS : params,
            })
            self._dispatcher_event.notify_all()

        return True


    def drive(self, steering, throttle, duration = 0.0, flipped = False, override = False):
        with self._state_mutex:
            if not self.is_ready():
                return False

        steering = max(min(steering, 90.0), -90.0)
        throttle = max(min(throttle, 1.0), -1.0)
        duration = max(min(duration, 5.0), 0.0)
        override = (override == True)
        flipped  = (flipped == True)

        with self._dispatcher_mutex:
            params = (steering, throttle, duration, flipped)

            if override:
                self._dispatcher_requests = []
            else:
                for request in reversed(self._dispatcher_requests):
                    if request[self.REQUEST_COMMAND] == self.REQUEST_COMMAND_DRIVE:
                        if request[self.REQUEST_PARAMS] == params:
                            # aggregate the repeated commands
                            request[self.REQUEST_UPDATED ]  = monotonic()
                            request[self.REQUEST_COUNT   ] += 1
                            return True
                        break

            while len(self._dispatcher_requests) >= self.MAX_QUEUED_DRIVE_COMMANDS:
                self._dispatcher_event.notify_all()
                self._dispatcher_event.wait()

                if not self.is_ready():
                    return False

            self._dispatcher_requests.append({
                self.REQUEST_CREATED: monotonic(),
                self.REQUEST_UPDATED: monotonic(),
                self.REQUEST_COUNT  : 1,
                self.REQUEST_COMMAND: self.REQUEST_COMMAND_DRIVE,
                self.REQUEST_PARAMS : params,
            })
            self._dispatcher_event.notify_all()

        return True


    def get_snapshot(self, ndx = 0):
        return self._model.get_snapshot(ndx)


    def get_all_snapshots(self):
        return self._model.get_snapshot()


    def get_frame_width(self, ndx = 0):
        return self._model.get_frame_width(ndx)


    def get_frame_height(self, ndx = 0):
        return self._model.get_frame_height(ndx)


    def get_frame_rate(self, ndx = 0):
        return self._model.get_frame_rate(ndx)


    def vibrate(self, count, interval = 0):
        return self._model.vibrate(count, interval)


    def ready_to_go(self):
        return self._model.ready_to_go()


if __name__ == "__main__":
    _BASEDIR = os.path.dirname(os.path.realpath(__file__))
    config.load(os.path.join(_BASEDIR, "..", "config.ini"))
    setloglevel(config.get("DEFAULT", "log_level", "DEBUG").strip())

    ctrl = Control(model_name = "TrendCarModel")
    ctrl.begin()
    ctrl.drive(-45, 1.0)
    ctrl.drive(-45, 1.0)
    ctrl.drive(-45, 1.0)
    ctrl.wait_for_requests_done()
    try:
        import cv2
        while True:
            #frames = ctrl.get_snapshots()
            #cv2.imshow("test", frames[0])
            cv2.waitKey(100)
    except:
        error_exc("exception occurred")

    ctrl.end()

