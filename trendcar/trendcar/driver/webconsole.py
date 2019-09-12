from common.stuff import *

import json
import socket
import threading

try:
    import SocketServer
except:
    import socketserver as SocketServer


class WebConsole(SocketServer.BaseRequestHandler):
    _DEF_HOST                 = "0.0.0.0"
    _DEF_PORT                 = 9999
    _DEF_JPEG_QUALITY_LEVEL   = 80  # JPEG quality level: 0 - 100
    _DEF_IMAGE_RENEW_INTERVAL = 250
    _DEF_MAX_IDLE_TAKING_OVER = 3
    _jpeg_quality_level       = _DEF_JPEG_QUALITY_LEVEL
    _image_renew_interval     = _DEF_IMAGE_RENEW_INTERVAL
    _max_idle_taking_over     = _DEF_MAX_IDLE_TAKING_OVER

    STATE_INIT                = 0
    STATE_STARTING            = 1
    STATE_STARTED             = 2
    STATE_STOPPING            = 3
    STATE_STOPPED             = 4
    _mutex                    = threading.Lock()
    _event                    = threading.Condition(_mutex)
    _thread                   = None
    _state                    = STATE_INIT

    _control                  = None
    _taking_over              = False
    _taking_over_started      = None
    _basedir                  = os.path.dirname(os.path.realpath(__file__))
    _snapshot_folder          = os.path.join(_basedir, "log", "snapshots")
    _recording_folder         = os.path.join(_basedir, "log", "recordings")
    _dashboard                = {}
    _last_frame               = None
    _drive_info               = {"steering": 0.0, "throttle": 0.0}

    _http_server              = None
    _cached_files             = {}
    _static_files             = {"/": "webconsole.html", "/joy.js": "joy.js"}


    @staticmethod
    def attach_control(control):
        WebConsole.detach_control()
        if control:
            control.register_dashboard_observer(WebConsole._on_pre_observe_dashboard , priority = Control.DASHBOARD_PRIORITY_HIGH)
            control.register_dashboard_observer(WebConsole._on_post_observe_dashboard, priority = Control.DASHBOARD_PRIORITY_LOW )
        WebConsole._control = control
        return True


    @staticmethod
    def detach_control():
        if WebConsole._control is not None:
            WebConsole._control.unregister_dashboard_observer(WebConsole._on_pre_observe_dashboard)
            WebConsole._control.unregister_dashboard_observer(WebConsole._on_post_observe_dashboard)
            WebConsole._control = None
            return True
        return False


    @staticmethod
    def set_host(host):
        config.set("WEBCONSOLE", "bind_addr", host)


    @staticmethod
    def get_host():
        return config.get("WEBCONSOLE", "bind_addr", WebConsole._DEF_HOST)


    @staticmethod
    def set_port(port):
        config.set("WEBCONSOLE", "listen_port", int(port))


    @staticmethod
    def get_port():
        return config.getint("WEBCONSOLE", "listen_port", WebConsole._DEF_PORT)


    @staticmethod
    def start(control = None):
        with WebConsole._mutex:
            while WebConsole._state in (WebConsole.STATE_STARTING, WebConsole.STATE_STOPPING):
                WebConsole._event.wait()

            if WebConsole._state == WebConsole.STATE_STARTED:
                return True

            if WebConsole._state in (WebConsole.STATE_STOPPED, WebConsole.STATE_INIT):
                WebConsole._state = WebConsole.STATE_STARTING
                WebConsole._event.notify_all()

        try:
            if control is not None:
                WebConsole.attach_control(control)

            WebConsole._thread = threading.Thread(target = WebConsole.serve, name = "WebConsole")
            WebConsole._thread.start()
        except:
            if control is not None:
                WebConsole.detach_control()

            with WebConsole._mutex:
                WebConsole._state = WebConsole.STATE_STOPPED
                WebConsole._event.notify_all()

            error_exc("Unable to start webconsole thread")
            return False

        with WebConsole._mutex:
            while WebConsole._state == WebConsole.STATE_STARTING:
                WebConsole._event.wait()
            started = WebConsole._state == WebConsole.STATE_STARTED

        if not started and control is not None:
            WebConsole.detach_control()

        return started


    @staticmethod
    def stop():
        with WebConsole._mutex:
            while WebConsole._state in (WebConsole.STATE_STARTING, WebConsole.STATE_STOPPING):
                try:
                    WebConsole._event.wait()
                except:
                    pass

            if WebConsole._state in (WebConsole.STATE_STOPPED, WebConsole.STATE_INIT):
                return True

            WebConsole._taking_over = False
            WebConsole._state = WebConsole.STATE_STOPPING
            WebConsole._event.notify_all()

        with WebConsole._mutex:
            while WebConsole._state == WebConsole.STATE_STOPPING:
                try:
                    WebConsole._event.wait()
                except:
                    pass

            stopped = WebConsole._state == WebConsole.STATE_STOPPED

        if stopped and WebConsole._thread:
            WebConsole._thread.join()
            WebConsole._thread = None

        WebConsole.detach_control()
        return stopped


    @staticmethod
    def serve():
        set_thread_name("WebConsole.serve")
        WebConsole._jpeg_quality_level   = config.getint("WEBCONSOLE", "jpeg_quality_level"          , WebConsole._DEF_JPEG_QUALITY_LEVEL)
        WebConsole._image_renew_interval = config.getint("WEBCONSOLE", "image_renewing_interval_ms"  , WebConsole._DEF_IMAGE_RENEW_INTERVAL)
        WebConsole._max_idle_taking_over = config.getint("WEBCONSOLE", "max_idle_seconds_taking_over", WebConsole._DEF_MAX_IDLE_TAKING_OVER)
        WebConsole._snapshot_folder      = config.get   ("DEFAULT"   , "snapshot_folder"             , os.path.join(WebConsole._basedir, "log", "snapshots"))
        WebConsole._recording_folder     = config.get   ("DEFAULT"   , "recording_folder"            , os.path.join(WebConsole._basedir, "log", "recordings"))

        if WebConsole._http_server:
            try:
                WebConsole._http_server.server_close()
            except:
                warn_exc("WebConsole: Exception occurred while closing http server")

            WebConsole._http_server = None

        try:
            with WebConsole._mutex:
                try:
                    SocketServer.TCPServer.allow_reuse_address = True
                    WebConsole._http_server = SocketServer.TCPServer((WebConsole.get_host(), WebConsole.get_port()), WebConsole)
                    WebConsole._http_server.timeout = 1

                    WebConsole._state = WebConsole.STATE_STARTED
                    WebConsole._event.notify_all()

                    if hwinfo.is_running_in_pi():
                        allow_incoming_ipv4_tcp(WebConsole.get_port())

                except:
                    error_exc("WebConsole: Failed to start http server")

            if WebConsole._http_server:
                info("WebConsole: started, listening on %s:%d", WebConsole.get_host(), WebConsole.get_port())
                while WebConsole._state == WebConsole.STATE_STARTED:
                    try:
                        WebConsole._http_server.handle_request()
                    except KeyboardInterrupt:
                        info("WebConsole: http server interrupted")
                        break
                    except:
                        warn_exc("WebConsole: Exception occurred at handle_request")

        finally:
            if WebConsole._http_server:
                try:
                    WebConsole._http_server.server_close()
                except:
                    warn_exc("WebConsole: Exception occurred while closing http server")

                WebConsole._http_server = None

            with WebConsole._mutex:
                WebConsole._state = WebConsole.STATE_STOPPED
                WebConsole._event.notify_all()
                info("WebConsole: stopped")

            if hwinfo.is_running_in_pi():
                os.system("sudo iptables -F IN_TRENDCAR")
                os.system("sudo iptables -A IN_TRENDCAR -j RETURN")


    @staticmethod
    def set_taking_over(taking_over):
        WebConsole._taking_over = taking_over
        WebConsole._taking_over_started = monotonic() if taking_over else None


    @staticmethod
    def get_taking_over():
        return WebConsole._taking_over


    @staticmethod
    def set_recording(recording):
        if recording:
            AutoPilot.start_recording()
        else:
            AutoPilot.stop_recording()


    @staticmethod
    def is_recording():
        return AutoPilot.is_recording()


    @staticmethod
    def _get_latest_frame():
        frame = WebConsole._dashboard.get("frame", None)
        if frame is not None:
            ret, frame = cv2.imencode('.jpg', frame , [cv2.IMWRITE_JPEG_QUALITY, WebConsole._jpeg_quality_level])
            if ret:
                WebConsole._last_frame = frame

        return frame


    @staticmethod
    def _get_any_frame():
        frame = WebConsole._get_latest_frame()
        if frame is None:
            frame = WebConsole._last_frame 

        if frame is None:
            frame_width  = WebConsole._dashboard.get("frame_width" , 320)
            frame_height = WebConsole._dashboard.get("frame_height", 240)
            frame        = np.zeros((frame_width, frame_height, 3), np.uint8)
        return frame


    @staticmethod
    def _snapshot_frame(folder, filename, frame = None):
        jpegfile = os.path.join(folder, filename)

        try:
            if not os.path.exists(folder):
                os.makedirs(folder)

            if os.path.isdir(folder):
                if frame is None:
                    frame = WebConsole._get_latest_frame()

                if frame is not None:
                    with open(jpegfile, "wb") as f:
                        f.write(frame)
                return True
        except:
            warn_exc("Unable to take snapshot %s in %s", filename, subdir) 

        return False


    @staticmethod
    def _get_track_view():
        track_view = WebConsole._dashboard.get("track_view", None)

        if track_view is not None:
            ret, track_view = cv2.imencode('.jpg', track_view , [cv2.IMWRITE_JPEG_QUALITY, WebConsole._jpeg_quality_level])
            if not ret:
                track_view = None

        if track_view is None:
            frame_width  = WebConsole._dashboard.get("frame_width" , 320)
            frame_height = WebConsole._dashboard.get("frame_height", 240)
            track_view   = np.zeros((frame_width, frame_height, 3), np.uint8)

        return track_view


    @staticmethod
    def _on_pre_observe_dashboard(dashboard):
        if WebConsole._taking_over:
            start = WebConsole._taking_over_started
            if start is not None and monotonic() - start >= WebConsole._max_idle_taking_over:
                WebConsole._taking_over        = False
                WebConsole._taking_over_stared = None

        if WebConsole._taking_over:
            WebConsole._dashboard = dashboard

            if WebConsole.is_recording():
                suffix = ",s={steering:+06.2f},t={throttle:+06.3f}".format(**WebConsole._drive_info)
                WebConsole._snapshot_frame(WebConsole._recording_folder, "recording-%s-webc%s.jpg" % (datetime.now().strftime("%Y%m%d-%H%M%S.%f"), suffix))

        return WebConsole._taking_over


    @staticmethod
    def _on_post_observe_dashboard(dashboard):
        if not WebConsole._taking_over:
            WebConsole._dashboard = dashboard

        return False


    @staticmethod
    def _get_file_content(filename):
        try:
            if filename not in WebConsole._cached_files:
                with open(os.path.join(WebConsole._basedir, filename), "rb") as f:
                    WebConsole._cached_files[filename] = f.read()

            return WebConsole._cached_files[filename]
        except:
            warn_exc("Unable to load file %s", os.path.join(WebConsole._basedir, filename))

        return None


    def handle(self):
        req  = []
        path = None

        try:
            req = self.request.recv(1024).decode('iso8859-1').strip().split("\n")

            if len(req) > 0 and req[0].upper().startswith("GET"):
                uri, httpver = req[0].split(' ', 1)[1:][0].rsplit(' ', 1)

                if len(httpver.strip()) == 8 and httpver.strip().upper().startswith("HTTP/") and httpver[6] == ".":
                    path = uri

        except:
            warn_exc("Unknown HTTP request:", req[0] if len(req) > 0 else "<empty>")
            self.send500("Unknown HTTP request")
            return

        if path == None:
            self.send500("Unrecognized HTTP request")
            return

        try:
            result = urlparse(path)
            path   = result.path.strip()
            params = dict((q.split("=", 1) + [''])[:2] for q in result.query.strip().split("&"))

            if path == "/camera.jpg":
                self.send200(self._get_any_frame().tostring(), "image/jpeg")
                return

            if path == "/track_view.jpg":
                self.send200(self._get_track_view().tostring(), "image/jpeg")
                return

            if path == "/photo":
                photo_filename = "photo-%s.jpg" % (datetime.now().strftime("%Y%m%d-%H%M%S.%f"))
                frame = self._get_any_frame()

                if self._snapshot_frame(WebConsole._snapshot_folder, photo_filename, frame = frame):
                    self.send200("""{"filename": "%s"}""" % photo_filename, "application/json")
                else:
                    self.send500("Photo was not saved")
                return

            if path == "/recording":
                if "stop" in params:
                    self.set_recording(False)
                elif "start" in params:
                    self.set_recording(True)

                self.send200("""{"recording": %s}""" % str(self.is_recording()).lower(), "application/json")
                return

            if path == '/live':
                frame_width  = WebConsole._dashboard.get("frame_width" , 0)
                frame_height = WebConsole._dashboard.get("frame_height", 0)

                self.send200("""<html><head><script language="JavaScript"><!--\n"""
                            """function refresh() {\n"""
                            """ document.getElementById("track_view").src = "/track_view.jpg?" + Math.random();\n"""
                            """ var camera = new Image();\n"""
                            """ camera.onload = function() {\n"""
                            """     var url = "/info";\n"""
                            """     var request = new XMLHttpRequest();\n"""
                            """     request.open("GET", url);\n"""
                            """     request.onload = function(e) {\n"""
                            """         if (request.readyState == 4 && request.status == 200 && request.getResponseHeader("content-type") ==="application/json") {\n"""
                            """             result = JSON.parse(this.responseText);\n"""
                            """             info = document.getElementById("info");\n"""
                            """             info.innerText = "" + result.frame_width + "x" + result.frame_height + " @" + parseFloat(result.frame_rate).toFixed(2) + " fps [autodrive " + result.autodrive + "]";\n"""
                            """             canvas        = document.getElementById("camera");\n"""
                            """             canvas.width  = camera.width;\n"""
                            """             canvas.height = camera.height;\n"""
                            """             ctx           = canvas.getContext("2d");\n"""
                            """             ctx.drawImage(camera, 0, 0);\n"""
                            """             if (result.focused_rect) {\n"""
                            """                 x1 = result.focused_rect[0];\n"""
                            """                 y1 = result.focused_rect[1];\n"""
                            """                 x2 = result.focused_rect[2];\n"""
                            """                 y2 = result.focused_rect[3];\n"""
                            """                 ctx.rect(x1, y1, x2, y2);\n"""
                            """                 ctx.lineWidth   = 3;\n"""
                            """                 ctx.strokeStyle = "red";\n"""
                            """                 ctx.setLineDash([4, 2]);\n"""
                            """                 ctx.stroke();\n"""
                            """                 if (result.focused_nr_rect) {\n"""
                            """                     ctx.font = "16px Arial";\n"""
                            """                     ctx.fillStyle = "red";\n"""
                            """                     ctx.fillText("#"+result.focused_nr_rect, x1 + 1, y1 + 17);\n"""
                            """                 }\n"""
                            """             }\n"""
                            """             if (result.track_view_info) {\n"""
                            """                 ctx.beginPath();\n"""
                            """                 ctx.moveTo(0, result.track_view_info[0]);\n"""
                            """                 ctx.lineTo(canvas.width, result.track_view_info[0]);\n"""
                            """                 ctx.moveTo(0, result.track_view_info[1] - 1);\n"""
                            """                 ctx.lineTo(canvas.width, result.track_view_info[1] - 1);\n"""
                            """                 ctx.lineWidth   = 1;\n"""
                            """                 ctx.strokeStyle = "yellow";\n"""
                            """                 ctx.setLineDash([4, 2, 2, 2]);\n"""
                            """                 ctx.stroke();\n"""
                            """                 if (typeof(result.track_view_info[2]) == "number" && typeof(result.track_view_info[2]) != NaN) {\n"""
                            """                     angle = (90.0 - parseFloat(result.track_view_info[2])) * Math.PI / 180.0;\n"""
                            """                     r = (canvas.height - result.track_view_info[0]) * 0.9;\n"""
                            """                     x = canvas.width/2 + r * Math.cos(angle);\n"""
                            """                     y = canvas.height  - r * Math.sin(angle);\n"""
                            """                     ctx.beginPath();\n"""
                            """                     ctx.moveTo(canvas.width/2, canvas.height);\n"""
                            """                     ctx.lineTo(x, y);\n"""
                            """                     ctx.lineWidth   = 2;\n"""
                            """                     ctx.strokeStyle = "magenta";\n"""
                            """                     ctx.setLineDash([4, 2]);\n"""
                            """                     ctx.stroke();\n"""
                            """                 }\n"""
                            """             }\n"""
                            """         }\n"""
                            """     }\n"""
                            """     request.send(null);\n"""
                            """ }\n"""
                            """ camera.src = "/camera.jpg?" + Math.random();\n"""
                            """ setTimeout("refresh()", %d);\n""" % (self._image_renew_interval) +
                            """}\n"""
                            """//--></script></head>\n"""
                            """<body onload="setTimeout('refresh()', %d)">\n""" % (self._image_renew_interval) +
                            """<center>"""
                            """<canvas style="display:block" id="camera" width="%d" height="%d"></canvas>""" % (frame_width, frame_height) +
                            """<div id="info">[]</div>"""
                            """<img id="track_view" src="/track_view.jpg"/>"""
                            """</center>\n"""
                            """</body></html>\n"""
                )
                return

            if path == "/info":
                self.send200(json.dumps({
                    "frame_width"    : WebConsole._dashboard.get("frame_width"    , 0   ),
                    "frame_height"   : WebConsole._dashboard.get("frame_height"   , 0   ),
                    "frame_rate"     : WebConsole._dashboard.get("frame_rate"     , 0.0 ),
                    "track_view_info": WebConsole._dashboard.get("track_view_info", None),
                    "focused_rect"   : WebConsole._dashboard.get("focused_rect"   , None),
                    "focused_nr_rect": WebConsole._dashboard.get("focused_nr_rect", None),
                    "autodrive"      : "started" if AutoPilot.get_autodrive_started() else "stopped",
                }), "application/json")
                return

            if path == "/drive":
                steering = float(params["steering"]) if "steering" in params else 0.0
                throttle = float(params["throttle"]) if "throttle" in params else 0.0
                WebConsole._drive_info = {"steering": steering, "throttle": throttle}

                if self._control.drive(steering, throttle):
                    self.set_taking_over(True)

                    self.send200(json.dumps({
                        "steering": steering,
                        "throttle": throttle,
                    }), "application/json")
                else:
                    self.send500("Unable to drive with parameters: %s" % (params))

                return

            if path == "/autodrive":
                if "stop" in params:
                    AutoPilot.stop_autodrive()
                elif "start" in params:
                    AutoPilot.start_autodrive()

                self.send200("""{"autodrive": "%s"}""" % ("started" if AutoPilot.get_autodrive_started() else "stopped"), "application/json")
                return

            if path in self._static_files:
                content = self._get_file_content(self._static_files[path])
                if content:
                    self.send200(content)
                    return

            self.send404("File not found: %s" % path)

        except:
            warn_exc("Unsuccessful action: %s", path)
            self.send500("Unsuccessful action: %s" % path)


    def send200(self, content, content_type = "text/html"):
        try:
            if bytes is not str and type(content) is str:
                content = content.encode('iso8859-1')

            self.request.sendall(b'HTTP/1.0 200 OK\nContent-Type: %s\n\n%s' % (content_type.encode('iso8859-1'), content))
        except OSError: #ConnectionResetError (py3), BrokenPipeError (py3)
            pass
        except socket.error:
            pass
        except:
            debug_exc("WebConsole: send200 exception")


    def send404(self, content):
        try:
            if content[0] != "<":
                content = "<html><body>%s</body></html>"
            
            self.request.sendall(b'HTTP/1.0 404 Not Found\nContent-Type: text/html\n\n%s' % (content.encode('iso8859-1')))
        except OSError: #ConnectionResetError (py3), BrokenPipeError (py3)
            pass
        except socket.error:
            pass
        except:
            debug_exc("WebConsole: send404 exception")


    def send500(self, content):
        try:
            if content[0] != "<":
                content = "<html><body>%s</body></html>"
            
            self.request.sendall(b'HTTP/1.0 500 ERROR\nContent-Type: text/html\n\n%s' % (content.encode('iso8859-1')))
        except OSError: #ConnectionResetError (py3), BrokenPipeError (py3)
            pass
        except socket.error:
            pass
        except:
            debug_exc("WebConsole: send500 exception")


if __name__ == "__main__":
    with Control.auto_detect() as control:
        if control is None:
            error("No car controls could be initiated")
            sys.exit(1)

        WebConsole.attach_control(control)

        try:
            WebConsole.serve()
        finally:
            WebConsole.detach_control()

    sys.exit(0)

