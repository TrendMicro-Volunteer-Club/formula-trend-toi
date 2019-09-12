from common.stuff import *

import os
import tty
import fcntl
import select
import socket
import termios
import threading

class TextConsole:
    DEF_CTRL_SOCKET           = "/tmp/trendcar-ctrl.sock"
    DEF_MAX_IDLE_TAKING_OVER  = 3
    DEF_MAX_IDLE_DEACTIVATING = 1.5

    SUCCESS                   = 0
    ERR_CONNECTION_NOT_READY  = 1
    ERR_SEND_COMMAND          = 2
    ERR_READ_SCRIPT           = 3

    STATE_INIT                = 0
    STATE_STARTING            = 1
    STATE_STARTED             = 2
    STATE_STOPPING            = 3
    STATE_STOPPED             = 4
    _serving_mutex            = threading.Lock()
    _serving_event            = threading.Condition(_serving_mutex)
    _serving_thread           = None
    _serving_state            = STATE_INIT

    _driving_mutex            = threading.Lock()
    _driving_event            = threading.Condition(_driving_mutex)
    _driving_thead            = None
    _driving_state            = STATE_INIT
    _driving_last_activated   = None
    _max_idle_deactivating    = DEF_MAX_IDLE_DEACTIVATING
    _steering                 = 0.0
    _throttle                 = 0.0

    _control                  = None
    _taking_over              = False
    _taking_over_started      = None
    _max_idle_taking_over     = DEF_MAX_IDLE_TAKING_OVER
    _dashboard                = {}

    _ctrl_socket_path         = None
    _ctrl_socket              = None
    _client_context           = {}


    @staticmethod
    def attach_control(control):
        TextConsole.detach_control()
        if control:
            control.register_dashboard_observer(TextConsole._on_pre_observe_dashboard , priority = Control.DASHBOARD_PRIORITY_HIGH)
            control.register_dashboard_observer(TextConsole._on_post_observe_dashboard, priority = Control.DASHBOARD_PRIORITY_LOW )
        TextConsole._control = control
        return True


    @staticmethod
    def detach_control():
        if TextConsole._control is not None:
            TextConsole._control.unregister_dashboard_observer(TextConsole._on_pre_observe_dashboard)
            TextConsole._control.unregister_dashboard_observer(TextConsole._on_post_observe_dashboard)
            TextConsole._control = None
            return True
        return False

    @staticmethod
    def start(control = None):
        with TextConsole._serving_mutex:
            while TextConsole._serving_state in (TextConsole.STATE_STARTING, TextConsole.STATE_STOPPING):
                TextConsole._serving_event.wait()

            if TextConsole._serving_state == TextConsole.STATE_STARTED:
                return True

            if TextConsole._serving_state in (TextConsole.STATE_STOPPED, TextConsole.STATE_INIT):
                TextConsole._serving_state = TextConsole.STATE_STARTING
                TextConsole._serving_event.notify_all()

            try:
                if control is not None:
                    TextConsole.attach_control(control)

                TextConsole._serving_thread = threading.Thread(target = TextConsole.serving_loop, name = "tc.serving_loop")
                TextConsole._serving_thread.start()

                TextConsole._driving_thread = threading.Thread(target = TextConsole.driving_loop, name = "tc.driving_loop")
                TextConsole._driving_thread.start()
            except:
                error_exc("Unable to start text console thread")

                if control is not None:
                    TextConsole.detach_control()

                with TextConsole._driving_mutex:
                    TextConsole._driving_state = TextConsole.STATE_STOPPED
                    TextConsole._driving_event.notify_all()

                with TextConsole._serving_mutex:
                    TextConsole._serving_state = TextConsole.STATE_STOPPED
                    TextConsole._serving_event.notify_all()

                return False

        with TextConsole._driving_mutex:
            while TextConsole._driving_state == TextConsole.STATE_STARTING:
                TextConsole._driving_event.wait()
            started = TextConsole._driving_state == TextConsole.STATE_STARTED

        with TextConsole._serving_mutex:
            while TextConsole._serving_state == TextConsole.STATE_STARTING:
                TextConsole._serving_event.wait()
            started = TextConsole._serving_state == TextConsole.STATE_STARTED

        if not started and control is not None:
            TextConsole.detach_control()

        return started


    @staticmethod
    def stop():
        with TextConsole._driving_mutex:
            while TextConsole._driving_state in (TextConsole.STATE_STARTING, TextConsole.STATE_STOPPING):
                TextConsole._driving_event.wait()

            if TextConsole._driving_state not in (TextConsole.STATE_STOPPED, TextConsole.STATE_INIT):
                TextConsole._driving_state = TextConsole.STATE_STOPPING
                TextConsole._driving_event.notify_all()

        with TextConsole._serving_mutex:
            while TextConsole._serving_state in (TextConsole.STATE_STARTING, TextConsole.STATE_STOPPING):
                TextConsole._serving_event.wait()

            if TextConsole._serving_state not in (TextConsole.STATE_STOPPED, TextConsole.STATE_INIT):
                TextConsole._taking_over = False
                TextConsole._serving_state = TextConsole.STATE_STOPPING

                if TextConsole._ctrl_socket:
                    try:
                        TextConsole._ctrl_socket.close()
                    except:
                        pass

                TextConsole._serving_event.notify_all()

        with TextConsole._driving_mutex:
            TextConsole._driving_event.notify_all()

            while TextConsole._driving_state == TextConsole.STATE_STOPPING:
                TextConsole._driving_event.wait()

            driving_thread_stopped = TextConsole._driving_state == TextConsole.STATE_STOPPED

        if driving_thread_stopped and TextConsole._driving_thread:
            TextConsole._driving_thread.join()
            TextConsole._driving_thread = None

        with TextConsole._serving_mutex:
            TextConsole._serving_event.notify_all()

            while TextConsole._serving_state == TextConsole.STATE_STOPPING:
                TextConsole._serving_event.wait()

            serving_thread_stopped = TextConsole._serving_state == TextConsole.STATE_STOPPED

        if serving_thread_stopped and TextConsole._serving_thread:
            TextConsole._serving_thread.join()
            TextConsole._serving_thread = None

        TextConsole.detach_control()
        return driving_thread_stopped and serving_thread_stopped


    @staticmethod
    def serving_loop():
        set_thread_name(TextConsole._serving_thread.getName())
        try:
            with TextConsole._serving_mutex:
                try:
                    TextConsole._ctrl_socket_path = config.get("TEXTCONSOLE", "ctrl_socket", TextConsole.DEF_CTRL_SOCKET)

                    if os.path.exists(TextConsole._ctrl_socket_path):
                        os.remove(TextConsole._ctrl_socket_path)

                    try:
                        TextConsole._ctrl_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        TextConsole._ctrl_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        TextConsole._ctrl_socket.bind(TextConsole._ctrl_socket_path)
                        TextConsole._ctrl_socket.listen(5)
                    except:
                        error_exc("TextConsole: Failed to bind unix socket %s" % (TextConsole._ctrl_socket_path))
                        return False

                    TextConsole._serving_state = TextConsole.STATE_STARTED
                    TextConsole._serving_event.notify_all()
                except:
                    error_exc("TextConsole: Failed to start daemon")

            if TextConsole._ctrl_socket:
                info("TextConsole: Started, listening on %s", TextConsole._ctrl_socket_path)

                ctrl_socket_fd = TextConsole._ctrl_socket.fileno()
                readfds        = [ctrl_socket_fd]

                while TextConsole._serving_state == TextConsole.STATE_STARTED:
                    try:
                        try:
                            readable, _, _ = select.select([ctrl_socket_fd], [], [])

                            if ctrl_socket_fd not in readable:
                                continue
                        except:
                            continue

                        _client_sock, _ = TextConsole._ctrl_socket.accept()

                        if _client_sock is None:
                            continue

                        info("TextConsole: Client connection accepted - %s", repr(_client_sock))

                        try:
                            _client_mutex = threading.Lock()

                            TextConsole._client_context[_client_sock] = {
                                "client_sock": _client_sock,
                                "mutex"      : _client_mutex,
                                "event"      : threading.Condition(_client_mutex),
                                "state"      : TextConsole.STATE_STARTING,
                                "quiet"      : False,
                                "recvq"      : bytearray(),
                                "sendq"      : bytearray(),
                            }

                            TextConsole._client_context[_client_sock]["thread"] = threading.Thread(
                                target = TextConsole.process_command,
                                args = (_client_sock, TextConsole._client_context[_client_sock]),
                                name = "tc.process_cmd"
                            )
                            TextConsole._client_context[_client_sock]["thread"].start()
                        except:
                            _client_sock.close()
                            warn_exc("TextConsole: Client connection dropped - %s", repr(_client_sock))

                    except KeyboardInterrupt:
                        info("TextConsole: Daemon loop interrupted")
                        break
                    except:
                        warn_exc("TextConsole: Exception occurred in daemon loop")

                debug("TextConsole: Notifying clients")
                for ctx in TextConsole._client_context.values():
                    with ctx["mutex"]:
                        if ctx["state"] != TextConsole.STATE_STOPPED:
                            ctx["state"] = TextConsole.STATE_STOPPING
                            ctx["event"].notify_all()

                        try:
                            ctx["client_sock"].close()
                        except:
                            pass


                debug("TextConsole: Stopping clients")
                for ctx in TextConsole._client_context.values():
                    with ctx["mutex"]:
                            while ctx["state"] != TextConsole.STATE_STOPPED:
                                ctx["event"].wait()

                    ctx["thread"].join()
                    del TextConsole._client_context[ctx["client_sock"]]

        finally:
            if TextConsole._ctrl_socket:
                try:
                    TextConsole._ctrl_socket.close()
                except:
                    pass

            if TextConsole._ctrl_socket_path and os.path.exists(TextConsole._ctrl_socket_path):
                try:
                    os.remove(TextConsole._ctrl_socket_path)
                except:
                    pass

            with TextConsole._serving_mutex:
                TextConsole._serving_state = TextConsole.STATE_STOPPED
                TextConsole._serving_event.notify_all()
                info("TextConsole: Stopped")


    @staticmethod
    def _add_throttle(delta, limit = None):
        if delta != 0:
            with TextConsole._driving_mutex:
                if delta > 0:
                    TextConsole._throttle = min(TextConsole._throttle + delta, 1.0 if limit is None else limit)
                else:
                    TextConsole._throttle = max(TextConsole._throttle + delta, -1.0 if limit is None else limit)

                TextConsole._driving_last_activated = monotonic()
                TextConsole._driving_event.notify_all()
                sys.stdout.flush()

        return TextConsole._throttle


    @staticmethod
    def _set_throttle(value):
        if value != TextConsole._throttle:
            with TextConsole._driving_mutex:
                TextConsole._throttle = min(max(value, -1.0), 1.0)
                TextConsole._driving_last_activated = monotonic()
                TextConsole._driving_event.notify_all()
                sys.stdout.flush()

        return TextConsole._throttle


    @staticmethod
    def _add_steering(delta, limit = None):
        if delta != 0:
            with TextConsole._driving_mutex:
                if delta > 0:
                    TextConsole._steering = min(TextConsole._steering + delta, 90.0 if limit is None else limit)
                elif delta < 0:
                    TextConsole._steering = max(TextConsole._steering + delta, -90.0 if limit is None else limit)

                TextConsole._driving_last_activated = monotonic()
                TextConsole._driving_event.notify_all()

        return TextConsole._steering


    @staticmethod
    def _set_steering(value):
        if value != TextConsole._steering:
            with TextConsole._driving_mutex:
                TextConsole._steering = min(max(value, -90.0), 90.0)
                TextConsole._driving_last_activated = monotonic()
                TextConsole._driving_event.notify_all()

        return TextConsole._steering


    @staticmethod
    def driving_loop():
        set_thread_name(TextConsole._driving_thread.getName())
        try:
            with TextConsole._driving_mutex:
                if TextConsole._control is None:
                    error("TextConsole: Driving requires valid control")
                    return False

                TextConsole._driving_state = TextConsole.STATE_STARTED
                TextConsole._driving_event.notify_all()
                info("TextConsole: Driving loop started")

            while TextConsole._driving_state == TextConsole.STATE_STARTED:
                flipped   = TextConsole._dashboard.get("flipped", False)
                steering  = TextConsole._steering
                throttle  = TextConsole._throttle
                activated = TextConsole._driving_last_activated
                idle      = monotonic() - activated if activated else -1

                if idle < 0 or idle > TextConsole._max_idle_deactivating:
                    if steering > 0.0:
                        steering = TextConsole._add_steering(-2.0 * throttle, 0.0)
                    elif steering < 0.0:
                        steering = TextConsole._add_steering( 2.0 * throttle, 0.0)

                    if steering != 0.0:
                        throttle = TextConsole._add_throttle(-0.01, 0.0)
                    else:
                        throttle = TextConsole._add_throttle(-0.05, 0.0)

                if TextConsole._control.drive(steering, throttle, flipped = flipped):
                    debug("TextConsole: Drive with steering = %0.2f, throttle = %0.2f", steering, throttle)
                    TextConsole.set_taking_over(True)

                if TextConsole._driving_last_activated != activated:
                    continue

                with TextConsole._driving_mutex:
                    if TextConsole._steering == 0.0 and TextConsole._throttle == 0.0:
                        TextConsole._driving_event.wait()
                    else:
                        if idle < 0 or idle > TextConsole._max_idle_deactivating:
                            interval = 0.1
                        else:
                            interval = TextConsole._max_idle_deactivating

                        TextConsole._driving_event.wait(timeout = interval)

        finally:
            with TextConsole._driving_mutex:
                TextConsole._driving_state = TextConsole.STATE_STOPPED
                TextConsole._driving_event.notify_all()
                info("TextConsole: Driving loop stopped")


    @staticmethod
    def set_taking_over(taking_over):
        TextConsole._taking_over = taking_over
        TextConsole._taking_over_started = monotonic() if taking_over else None


    @staticmethod
    def get_taking_over():
        return TextConsole._taking_over


    @staticmethod
    def _on_pre_observe_dashboard(dashboard):
        TextConsole._dashboard = dashboard

        if TextConsole.get_taking_over():
            start = TextConsole._taking_over_started
            if start is not None and monotonic() - start >= TextConsole._max_idle_taking_over:
                TextConsole.set_taking_over(False)

        return TextConsole.get_taking_over()


    @staticmethod
    def _on_post_observe_dashboard(dashboard):
        TextConsole._dashboard = dashboard
        return False


    @staticmethod
    def _send_to_queue(client_context, data):
        with client_context["mutex"]:
            client_context["sendq"].extend(data)
            client_context["event"].notify_all()


    @staticmethod
    def _cmd_help(key, value, client_sock, client_context):
        TextConsole._send_to_queue(client_context,
               b"""# -- Trend Car Text Console --\n""" \
               b"""#\n""" \
               b"""# Supported key strokes/keywords:\n""" \
               b"""#   ?, h                                Display this help message\n""" \
               b"""#   m                                   Mute/Unmute the response\n""" \
               b"""#   ;                                   Report status\n""" \
               b"""#   w, i, <up>                          Throttle up\n""" \
               b"""#   s, k, <down>                        Throttle down\n""" \
               b"""#   a, j, <left>                        Steer left\n""" \
               b"""#   d, l, <right>                       Steer right\n""" \
               b"""#   <space>                             Brake\n""" \
               b"""#   <tab>                               Toggle autodrive mode\n""" \
               b"""#   ~                                   Toggle remote control mode\n""" \
               b"""#   q, <Ctrl-C>, <Ctrl-D>               Exit the text console\n""" \
               b"""#\n"""
        )


    @staticmethod
    def _cmd_mute(key, value, client_sock, client_context):
        client_context["quiet"] = not client_context["quiet"]


    @staticmethod
    def _send_state_updates(client_sock, client_context):
        if not client_context["quiet"]:
            TextConsole._send_to_queue(client_context, b"STATE: steering=%d, throttle=%0.2f, autodrive=%s, remotecontrol=%s\n" % (
                TextConsole._steering,
                TextConsole._throttle,
                b"started" if AutoPilot.get_autodrive_started()      else b"stopped",
                b"enabled" if AutoPilot.get_remote_control_enabled() else b"disabled",
            ))


    @staticmethod
    def _cmd_status(key, value, client_sock, client_context):
        TextConsole._send_state_updates(client_sock, client_context)


    @staticmethod
    def _cmd_up(key, value, client_sock, client_context):
        TextConsole.set_taking_over(True)

        if value is None:
            TextConsole._add_throttle(0.1)
        else:
            TextConsole._set_throttle(abs(value))

        TextConsole._send_state_updates(client_sock, client_context)


    @staticmethod
    def _cmd_down(key, value, client_sock, client_context):
        TextConsole.set_taking_over(True)

        if value is None:
            TextConsole._add_throttle(-0.1)
        else:
            TextConsole._set_throttle(-abs(value))

        TextConsole._send_state_updates(client_sock, client_context)


    @staticmethod
    def _cmd_right(key, value, client_sock, client_context):
        TextConsole.set_taking_over(True)

        if value is None:
            TextConsole._add_steering(10.0)
        else:
            TextConsole._set_steering(abs(value))

        TextConsole._send_state_updates(client_sock, client_context)


    @staticmethod
    def _cmd_left(key, value, client_sock, client_context):
        TextConsole.set_taking_over(True)

        if value is None:
            TextConsole._add_steering(-10.0)
        else:
            TextConsole._set_steering(-abs(value))

        TextConsole._send_state_updates(client_sock, client_context)


    @staticmethod
    def _cmd_brake(key, value, client_sock, client_context):
        TextConsole.set_taking_over(True)

        throttle = TextConsole._throttle

        if value is None:
            throttle = TextConsole._set_throttle(throttle / 4)
        else:
            throttle = TextConsole._set_throttle(throttle * (1.0 - max(min(abs(value), 1.0), 0.0)))

        if throttle == 0.0:
            TextConsole._set_steering(0.0)
        elif -0.1 <= throttle <= 0.1:
            TextConsole._set_throttle(0.0)

        TextConsole._send_state_updates(client_sock, client_context)


    @staticmethod
    def _cmd_autodrive(key, value, client_sock, client_context):
        if not AutoPilot.get_remote_control_enabled():
            started = AutoPilot.get_autodrive_started()

            if value is not None:
                if bool(value) == started:
                    return

                required_to_start = bool(value)
            else:
                required_to_start = not started

            if required_to_start:
                AutoPilot.start_autodrive()
            else:
                AutoPilot.stop_autodrive()
                TextConsole._set_steering(0.0)
                TextConsole._set_throttle(0.0)

        TextConsole._send_state_updates(client_sock, client_context)


    @staticmethod
    def _cmd_remotecontrol(key, value, client_sock, client_context):
        enabled = AutoPilot.get_remote_control_enabled()

        if value is not None:
            if bool(value) == enabled:
                return

            required_to_enable = bool(value)
        else:
            required_to_enable = not enabled

        if required_to_enable:
            AutoPilot.enable_remote_control()
        else:
            AutoPilot.disable_remote_control()

        TextConsole._set_steering(0.0)
        TextConsole._set_throttle(0.0)

        TextConsole._send_state_updates(client_sock, client_context)


    @staticmethod
    def _cmd_quit(key, value, client_sock, client_context):
        client_context["state"] = TextConsole.STATE_STOPPING


    _command_map = {
        "?"     : "help",
        "h"     : "help",
        'm'     : 'mute',
        ';'     : 'status',
        "\x1b[A": "up",
        "w"     : "up",
        "i"     : "up",
        "\x1b[B": "down",
        "s"     : "down",
        "k"     : "down",
        "\x1b[C": "right",
        "d"     : "right",
        "l"     : "right",
        "\x1b[D": "left",
        "a"     : "left",
        "j"     : "left",
        " "     : "brake",
        "\t"    : "autodrive",
        "~"     : "remotecontrol",
        "q"     : "quit",
    }

    _command_value = None


    @staticmethod
    def _get_next_command(cmdbuf):
        while len(cmdbuf) > 0:
            key = cmdbuf[0: 1].decode('iso8859-1')

            if key.isdigit() or key in ['+', '-', '.']:
                if TextConsole._command_value is None:
                    TextConsole._command_value = []
                TextConsole._command_value.append(key)
                del cmdbuf[0:1]
                continue

            value = None

            if TextConsole._command_value is not None:
                try:
                    debug("parsing %s", repr(TextConsole._command_value))

                    value = float("".join(TextConsole._command_value))
                    TextConsole._command_value = None
                except:
                    debug_exc("exception occurred while parsing %s", repr(TextConsole._command_value))


            if ord(key) == 0x1b: #ESC
                n = len(cmdbuf)

                if n == 1:
                    break

                if cmdbuf[1: 2].decode('iso8859-1') == '[':
                    if n >= 3:
                        key = cmdbuf[0: 3].decode('iso8859-1')
                        del cmdbuf[0: 3]
                        if key in TextConsole._command_map:
                            return TextConsole._command_map[key], key, value
                    break

            del cmdbuf[0:1]

            if key in TextConsole._command_map:
                return TextConsole._command_map[key], key, value

        return None, None, None


    @staticmethod
    def _sending_thread(client_sock, client_context):
        set_thread_name("tc.sending_thread")

        while client_context["state"] == TextConsole.STATE_STARTED:
            with client_context["mutex"]:
                if len(client_context["sendq"]) == 0:
                    client_context["event"].wait()
                    continue

                data = client_context["sendq"]
                client_context["sendq"] = bytearray()

            client_sock.send(data)


    @staticmethod
    def _receiving_thread(client_sock, client_context):
        set_thread_name("tc.receiving_thread")

        while client_context["state"] == TextConsole.STATE_STARTED:
            data = client_sock.recv(4096)

            if len(data) == 0:
                break

            with client_context["mutex"]:
                client_context["recvq"].extend(data)
                client_context["event"].notify_all()


    @staticmethod
    def process_command(client_sock, client_context):
        set_thread_name(client_context["thread"].getName())

        sending_thread   = None
        receiving_thread = None

        try:
            info("TextConsole: Started processing commands - %s", repr(client_sock))

            with client_context["mutex"]:
                if client_context["state"] != TextConsole.STATE_STARTING:
                    return

                client_context["state"] = TextConsole.STATE_STARTED
                client_context["event"].notify_all()


            sending_thread   = threading.Thread(target = TextConsole._sending_thread  , args = (client_sock, client_context), name = "tc.sending_thread"  )
            receiving_thread = threading.Thread(target = TextConsole._receiving_thread, args = (client_sock, client_context), name = "tc.receiving_thread")
            sending_thread.start()
            receiving_thread.start()

            try:
                cmdbuf = bytearray()
                TextConsole._cmd_help(None, None, client_sock, client_context)

                while client_context["state"] == TextConsole.STATE_STARTED:
                    with client_context["mutex"]:
                        if len(client_context["recvq"]) == 0:
                            client_context["event"].wait()
                            continue

                        data = client_context["recvq"]
                        client_context["recvq"] = bytearray()

                    if len(data) == 0:
                        break

                    cmdbuf.extend(data)
                    cmd, key, value = TextConsole._get_next_command(cmdbuf)

                    if cmd is not None:
                        try:
                            func = eval("TextConsole._cmd_%s" % cmd)
                            func(key, value, client_sock, client_context)
                        except:
                            error_exc("TextConsole: Exception occurred while executing command %s - %s", cmd, repr(client_sock))
                            continue

            except:
                error_exc("TextConsole: Exception occurred - %s", repr(client_sock))

        finally:
            info("TextConsole: Client connection closed - %s", repr(client_sock))

            try:
                client_sock.close()
            except:
                pass

            with client_context["mutex"]:
                client_context["state"] = TextConsole.STATE_STOPPED
                client_context["event"].notify_all()

            if sending_thread:
                sending_thread.join()

            if receiving_thread:
                receiving_thread.join()


    @staticmethod
    def console(cmd, script, interactive, quiet):
        _connected        = False
        _ctrl_socket      = None
        _ctrl_socket_path = config.get("TEXTCONSOLE", "ctrl_socket", TextConsole.DEF_CTRL_SOCKET)

        if not os.path.exists(_ctrl_socket_path):
            error("TextConsole: Control socket was not ready: %s", _ctrl_socket_path)
            return TextConsole.ERR_CONNECTION_NOT_READY  

        console_fd = sys.stdin.fileno()

        if sys.stdin.isatty():
            old_tty_attrs = termios.tcgetattr(console_fd)

        fcntl.fcntl(console_fd, fcntl.F_SETFL, os.O_NONBLOCK | fcntl.fcntl(console_fd, fcntl.F_GETFL))

        try:
            try:
                _ctrl_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

                if not _ctrl_socket:
                    error("TextConsole: Unable to create control socket")
                    return TextConsole.ERR_CONNECTION_NOT_READY  

                for tries in range(20):
                    try:
                        _ctrl_socket.connect(_ctrl_socket_path)
                        _connected = True
                        break
                    except:
                        debug_exc("TextConsole: Waiting for socket %s becoming ready", _ctrl_socket_path)

                    time.sleep(1)

                if not _connected:
                    error("TextConsole: Unable to connect to socket %s", _ctrl_socket_path)
                    return TextConsole.ERR_CONNECTION_NOT_READY

            except:
                error_exc("TextConsole: Exception occurred while connecting to control socket: %s", _ctrl_socket_path)
                return TextConsole.ERR_CONNECTION_NOT_READY  


            commands = []

            if quiet:
                _ctrl_socket.send(b'm')

            if script:
                try:
                    with open(script, "r") as f:
                        commands.append(f.read())
                except:
                    error_exc("TextConsole: Exception occurred while sending command to control socket: %s", _ctrl_socket_path)
                    return TextConsole.ERR_READ_SCRIPT

            if cmd:
                commands.append(cmd)

            if len(commands) > 0:
                for c in commands:
                    _ctrl_socket.send(c.encode('iso8859-1'))

                if not interactive:
                    return TextConsole.SUCCESS

            try:
                ctrl_socket_fd = _ctrl_socket.fileno()
                readfds        = [console_fd, ctrl_socket_fd]

                if sys.stdin.isatty():
                    tty.setcbreak(console_fd)

                while True:
                    readable, _, _ = select.select(readfds, [], [])

                    if console_fd in readable:
                        ch = os.read(console_fd, 1)

                        if len(ch) == 0:    # EOF
                            break
                        if sys.stdin.isatty() and ord(ch) in (3, 4): # EOF/Ctrl-D, or Ctrl-C
                            break

                        _ctrl_socket.send(ch)

                    if ctrl_socket_fd in readable:
                        buf = _ctrl_socket.recv(4096)

                        if len(buf) == 0:
                            break

                        if not quiet:
                            sys.stdout.write(buf.decode('iso8859-1'))
                            sys.stdout.flush()

            except KeyboardInterrupt:
                pass

        finally:
            if _ctrl_socket:
                _ctrl_socket.close()

            sys.stdout.flush()

            if sys.stdin.isatty():
                termios.tcsetattr(console_fd, termios.TCSADRAIN, old_tty_attrs)

        return TextConsole.SUCCESS

