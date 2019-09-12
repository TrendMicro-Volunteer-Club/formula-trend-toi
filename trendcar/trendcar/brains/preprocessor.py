from common.stuff      import *
from common            import imgutils

import threading
from collections import deque


@AutoPilot.register
class Preprocessor(AutoPilot):
    _top_view_range    = (0.00, 0.45)
    _middle_view_range = (0.45, 0.55)
    _bottom_view_range = (0.55, 1.00)
    _detect_interval   = 0.0
    _enable_detect_go  = True


    def __init__(self):
        self._detect_go_ready  = False
        self._last_detecting   = None

        if hwinfo.is_running_in_pi() and self._enable_detect_go:
            self._start_detect_go_proxy()


    def _split_roi(self, dashboard):
        if "frame" not in dashboard:
            return

        frame = dashboard["frame"]

        if frame is None:
            return

        top_view_slice    = slice(*(int(x * frame.shape[0]) for x in self._top_view_range))
        middle_view_slice = slice(*(int(x * frame.shape[0]) for x in self._middle_view_range))
        bottom_view_slice = slice(*(int(x * frame.shape[0]) for x in self._bottom_view_range))

        #top_view    = frame[top_view_slice, :, :]
        #middle_view = frame[middle_view_slice, :, :]
        bottom_view = frame[bottom_view_slice, :, :]

        #dashboard["top_view"   ] = top_view
        #dashboard["middle_view"] = middle_view
        #dashboard["bottom_view"] = bottom_view
        dashboard["track_view"     ] = imgutils.flatten_rgb(bottom_view)
        dashboard["track_view_info"] = (bottom_view_slice.start, bottom_view_slice.stop, None)


    @AutoPilot.priority_high
    def on_edit_dashboard(self, dashboard):
        self._split_roi(dashboard)
        return False


    @AutoPilot.priority_high
    def on_inquiry_drive(self, dashboard, last_result):
        if not hwinfo.is_running_in_pi():
            return None

        if self.get_remote_control_enabled() or self.get_autodrive_started():
            self.detect_go(None)
            self._detect_go_ready = False
            self._last_detecting  = None
            return None

        if self._enable_detect_go:
            now = monotonic()

            if self._last_detecting is None or now - self._last_detecting >= self._detect_interval:
                if dashboard.get("frame", None) is None:
                    return None

                detected, rect, nr_rect = self.detect_go(dashboard["frame"])

                if rect is not None:
                    dashboard["focused_rect"   ] = rect
                    dashboard["focused_nr_rect"] = nr_rect
                else:
                    dashboard["focused_rect"   ] = None
                    dashboard["focused_nr_rect"] = 0

                if detected is not None and nr_rect >= 0:
                    if not self._detect_go_ready:
                        self.vibrate(3)
                        self._detect_go_ready = True

                if detected is True:
                    info("Preprocessor: GO Detected!! RUN! Barry! RUN!")
                    self.detect_go(None)
                    self._detect_go_ready = False
                    self._last_detecting  = None
                    self.start_autodrive()
                    return None

                self._last_detecting = now

        return None


    _detect_go_proxy_thread = None
    _detect_go_frame        = None
    _detect_go_result       = (None, None, -1)
    _detect_go_proc         = None


    @staticmethod
    def detect_go(frame):
        if frame is None:
            Preprocessor._detect_go_frame  = None
            Preprocessor._detect_go_result = (None, None, -1)
            Preprocessor.close_detect_go()
            return (None, None, -1)

        result = Preprocessor._detect_go_result
        if result[0] in (None, False):
            if result[0] is None or result[2] < 0:
                info("Preprocessor: detect_go service was unready...")
            else:
                info("Preprocessor: GO was undetected")

            Preprocessor._detect_go_frame = frame

        return result


    @staticmethod
    def _start_detect_go_proxy():
        if Preprocessor._detect_go_proxy_thread is None:
            Preprocessor._detect_go_proxy_thread = threading.Thread(target = Preprocessor._detect_go_proxy)
            Preprocessor._detect_go_proxy_thread.setDaemon(True)
            Preprocessor._detect_go_proxy_thread.start()


    @staticmethod
    def _detect_go_proxy():
        set_thread_name("detect_go_proxy")

        Preprocessor.detect_go_sync(None)

        while True:
            result = Preprocessor._detect_go_result
            if result[0] is True:
                Preprocessor._detect_go_frame = None
                Preprocessor.close_detect_go()
                time.sleep(0.5)
                continue

            if Preprocessor._detect_go_frame is None:
                time.sleep(0.033)   #assume 30fps of max possible rate
                continue

            if Preprocessor._detect_go_result[0] is None:
                Preprocessor._detect_go_result = (False, None, -1)  # pseudo result

            frame = Preprocessor._detect_go_frame
            Preprocessor._detect_go_frame = None
            result = Preprocessor.detect_go_sync(frame)

            if Preprocessor._detect_go_result[0] is not None:
                Preprocessor._detect_go_result = result


    @staticmethod
    def detect_go_sync(frame):
        import os
        import struct
        import subprocess

        try:
            import cPickle as pickle
        except:
            import pickle

        try:
            if Preprocessor._detect_go_proc is None:
                Preprocessor._detect_go_proc = subprocess.Popen([sys.executable, os.path.realpath(__file__)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env = os.environ.copy())

            if frame is None:
                return False, None, 0

            start = monotonic()
            data = pickle.dumps(frame)
            Preprocessor._detect_go_proc.stdin.write(struct.pack("<I", len(data)))
            Preprocessor._detect_go_proc.stdin.write(data)

            n = int(*struct.unpack("<I", Preprocessor._detect_go_proc.stdout.read(4)))
            result = pickle.loads(Preprocessor._detect_go_proc.stdout.read(n))
            elapsed1 = monotonic() - start

            if result is not None:
                detected, rect_union, rect_count, elapsed2 = result
                debug("Preprocessor: detect_go returned %d candidates within the rectangle area %s in %0.4f seconds (actual processing time: %0.4f seconds, IO latency: %0.4f seconds)", rect_count, rect_union, elapsed1, elapsed2, elapsed1 - elapsed2)
                return detected, rect_union, rect_count

        except OSError: #BrokenPipeError in python 3
            pass
        except IOError:
            pass
        except struct.error:
            pass
        except:
            debug_exc("Preprocessor: Exception occurred in detect_go client")

        Preprocessor.close_detect_go()
        return False, None, 0


    @staticmethod
    def close_detect_go():
        proc = Preprocessor._detect_go_proc
        if proc:
            debug("Preprocessor: Stopping detect go service...")

            try:
                proc.send_signal(2) #SIGINT
                proc.poll()

                if proc.returncode is None:
                    proc.terminate()
                    proc.poll()
                    if proc.returncode is None:
                        proc.kill()
                        proc.poll()

                if proc.returncode is None:
                    debug("Preprocessor: Detect go service is still running...")
                else:
                    proc.wait()
                    Preprocessor._detect_go_proc = None
                    debug("Preprocessor: Detect go service stopped.")

            except OSError:
                Preprocessor._detect_go_proc = None
                debug("Preprocessor: Detect go service has been stopped.")


    @staticmethod
    def detect_go_service():
        set_thread_name("detect_go")

        import struct

        try:
            import cPickle as pickle
        except:
            import pickle

        fin  = get_stdin_binary_mode()
        fout = get_stdout_binary_mode()

        try:
            from brains.go.starter_hsv_rf import detect_go
            detect_go.msg_print = lambda self, msg: sys.stderr.write("Preprocessor: detect_go_service - %s\n" % (msg))
            _detect_go = detect_go()

            while True:
                try:
                    n = int(*struct.unpack('<I', fin.read(4)))
                    if n <= 0:
                        break
                except:
                    break

                frame = pickle.loads(fin.read(n))
                start = monotonic()
                detected, rect_list = _detect_go.detect(frame)
                elapsed = monotonic() - start

                rect_count = len(rect_list)
                if rect_count > 0:
                    y1, y2, x1, x2 = reduce(lambda a, b: (min(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3])), rect_list)
                    rect_union = (x1, y1, x2 - x1, y2 - y1)
                else:
                    rect_union = None

                result = pickle.dumps((detected, rect_union, rect_count, elapsed))

                fout.write(struct.pack('<I', len(result)))
                fout.write(result)
                fout.flush()

        except OSError: #BrokenPipeError in python 3
            pass
        except IOError:
            pass
        except struct.error:
            pass
        except:
            import traceback
            exc_msg = traceback.format_exc()
            sys.stderr.write("Preprocessor: Exception occurred in detect_go_service(): %s\n" % (exc_msg))


if __name__ == "__main__":
    Preprocessor.detect_go_service()

