#!/usr/bin/python

#
# Prerequisite on Raspbian:
#   sudo apt-get install -y python-paramiko
#   sudo pip install RPLCD
#
# Setup on the same trendcar SD image:
#   sudo systemctl disable trendcar
#   sudo systemctl stop trendcar
#   sudo python trendcar-fpv.py --install
#
# Dashboard wiring on PI
#   UART:
#       VCC(+5V)    --> Unconnected
#       GND         --> PIN 6  (GND)
#       RX          --> PIN 8  (TX)      
#       TX          --> PIN 10 (RX)
#
#   I2C LCD1602:
#       SDA         --> PIN 3 (SDA)
#       SCL         --> PIN 5 (SCL)
#       VCC(+5V)    --> PIN 2 (+5V)
#       GND         --> PIN 9 (GND)
#
#   Servo SG90S:
#       VCC(+5V)    --> PIN 4  (+5V)
#       GND         --> PIN 14 (GND)
#       PWM         --> PIN 7  (GPIO 7)
#

from __future__ import print_function

import os
import sys
import csv
import time
import math
import pygame
import paramiko
import StringIO
import threading

from glob        import glob
from collections import OrderedDict


def log(fmt, *arg):
    sys.stdout.write("%s\n" % (fmt % arg))
    sys.stdout.flush()


def debug(fmt, *arg):
    sys.stdout.write("[DEBUG] %s\n" % (fmt % arg))
    sys.stdout.flush()


def error_exc(fmt, *arg):
    import traceback
    exc_msg = traceback.format_exc()
    sys.stdout.write("[ERROR] %s - %s\n" % ((fmt % arg), exc_msg))
    sys.stdout.flush()


class Dashboard(object):
    SPEEDOMETER_SERVO_PIN      = 7
    SPEEDOMETER_SERVO_PWM_FREQ = 50
    LCD1602_I2C_ADDR           = 0x27

    def __init__(self):
        self._GPIO        = None
        self._speedometer = None
        self._lcd         = None

        try:
            import RPi.GPIO as GPIO
            self._GPIO = GPIO
            self._GPIO.setwarnings(False)
            self._GPIO.setmode(self._GPIO.BOARD)
            self._GPIO.setup(self.SPEEDOMETER_SERVO_PIN, self._GPIO.OUT)
            self._speedometer = self._GPIO.PWM(self.SPEEDOMETER_SERVO_PIN, self.SPEEDOMETER_SERVO_PWM_FREQ)
            self._speedometer.start(0)
        except:
            if self._GPIO:
                self._GPIO.cleanup()
                self._GPIO = None
                self._speedometer = None

        self._lcd_mutex = threading.Lock()

        try:
            from RPLCD.i2c import CharLCD
            self._lcd       = CharLCD('PCF8574', address = 0x27, port = 1, backlight_enabled = True)
        except:
            self._lcd = None


    def _set_degree(self, degree):
        if self._speedometer:
            self._speedometer.ChangeDutyCycle(3.1 + (13.8 - 3.1) * (max(min(180.0 - degree, 180.0), 0.0) / 180.0))


    def clear_display(self):
        with self._lcd_mutex:
            self._lcd.clear()


    def display(self, line = None, row = 0):
        if line:
            with self._lcd_mutex:
                self._lcd.cursor_pos = (row, 0)
                self._lcd.write_string(line)


    def show_logo(self):
        self._set_degree(0)
        self.display("   [TRENDCAR]   ", 0)
        self.display("    - FPV -     ", 1)


    def show_throttle(self, throttle):
        self._set_degree(abs(throttle) * 180.0)
        unit = abs(int(throttle * 7.0))
        bar  = (" " * (7 - unit)) + ("=" * unit) + "%02d" % (abs(int(throttle * 10))) + ("=" * unit) + (" " * (7 - unit))
        self.display(bar, 0)


    def show_steering(self, steering):
        unit      = int(steering / 90.0 * 7.0)
        left_bar  = (" " * (7 + min(unit, 0))) + ("<" * -min(unit, 0))
        right_bar = (">" * max(unit, 0)) + (" " * (7 - max(unit, 0)))
        bar       = left_bar + ("%02d" % (abs(int(steering)))) + right_bar
        self.display(bar, 1)


    def edit_ipv4(self, ipv4, ndx):
        os.system("clear")

        line = ""
        for i, n in enumerate(ipv4):
            if ndx == i:
                line += "%3d<" % (n)
            else:
                line += "%3d" % (n)
                if i < len(ipv4) - 1:
                    line += "."
                else:
                    line += " "

        self.display("IPv4 Address:   ", 0)
        self.display(line, 1)

        sys.stdout.write("IPv4 Address:\n")
        sys.stdout.write(line)
        sys.stdout.write("\n")


    def show_menu(self, menu, ndx):
        os.system("clear")

        if len(menu) == 0: 
            self.clear_display()
            self.display("(No Items)")
            sys.stdout.write("(No Items)\n")
        else:
            if ndx <= len(menu) - 2:
                start = ndx
            else:
                start = max(len(menu) - 2, 0)

            if start < len(menu):
                cursor = "> " if ndx == start else "  "
                self.display((cursor + menu[start]).ljust(16), 0)

            if start + 1 < len(menu):
                cursor = "> " if ndx == start + 1 else "  "
                self.display((cursor + menu[start + 1]).ljust(16), 1)
            else:
                self.display(" " * 16, 1)

            for i in range(len(menu)):
                if i == ndx:
                    sys.stdout.write(" > ")
                else:
                    sys.stdout.write("   ")

                sys.stdout.write(menu[i])
                sys.stdout.write("\n")

        sys.stdout.flush()


    def clear_menu(self):
        self.clear_display()
        os.system("clear")


    def show_message(self, msg):
        self.show_logo()
        self.display(msg.center(16), 1)
        os.system("clear")
        sys.stdout.write(msg)
        sys.stdout.write("\n")


    def show_progress(self, percentage):
        self.show_logo()
        n    = int(percentage * 13 / 100)
        tail = "-" if ((percentage * 13 / 100) - n) >= 0.5 else ""
        bar = ("%02d%%" % (int(percentage)) + "=" * n + tail).ljust(16, "_")
        self.display(bar, 1)


class JoyStick(object):
    DEFAULT                      = None
    LOGITECH_GXX_RACING_WHEEL    = "Racing Wheel"
    LOGITECH_GAMEPAD_F310_X_MODE = "Logitech Gamepad F310"
    LOGITECH_GAMEPAD_F310_D_MODE = "Logitech Dual Action"
    LOGITECH_MOMO_RACING         = "Logitech MOMO Racing"
    PROFILES                  = (
        (LOGITECH_GXX_RACING_WHEEL, {
            "axis": {
                0: {"key": "steering", "function": lambda x: round(x * 90.0, 2)},
                2: {"key": "throttle", "function": lambda x: round((1.0 - x) / 2.0, 2) if x != 0.0 else x},
                3: {"key": "brake"   , "function": lambda x: round((1.0 - x) / 2.0, 2) if x != 0.0 else x},
            },
            "button": {
                4: {"key": "next"    , "function": lambda x: bool(x)},
                5: {"key": "prev"    , "function": lambda x: bool(x)},
                6: {"key": "enter"   , "function": lambda x: bool(x)},
                7: {"key": "escape"  , "function": lambda x: bool(x)},
            },
        }),
        (LOGITECH_GAMEPAD_F310_X_MODE, {
            "axis": {
                1: {"key": "throttle", "function": lambda x: round(-x, 2)},
                3: {"key": "steering", "function": lambda x: round(x * 90.0, 2)},
            },
            "button": {
                4: {"key": "prev"    , "function": lambda x: bool(x)},
                5: {"key": "next"    , "function": lambda x: bool(x)},
                6: {"key": "escape"  , "function": lambda x: bool(x)},
                7: {"key": "enter"   , "function": lambda x: bool(x)},
            }
        }),
        (LOGITECH_GAMEPAD_F310_D_MODE, {
            "axis": {
                1: {"key": "throttle", "function": lambda x: round(-x, 2)},
                2: {"key": "steering", "function": lambda x: round(x * 90.0, 2)},
            },
            "button": {
                4: {"key": "prev"    , "function": lambda x: bool(x)},
                5: {"key": "next"    , "function": lambda x: bool(x)},
                8: {"key": "escape"  , "function": lambda x: bool(x)},
                9: {"key": "enter"   , "function": lambda x: bool(x)},
            }
        }),
        (LOGITECH_MOMO_RACING, {
            "axis": {
                0: {"key": "steering", "function": lambda x: round(x * 90.0, 2)},
                1: {"key": "throttle", "function": lambda x: round((1.0 - x) / 2.0, 2) if x != 0.0 else x},
                2: {"key": "brake"   , "function": lambda x: round((1.0 - x) / 2.0, 2) if x != 0.0 else x},
            },
            "button": {
                0: {"key": "prev"    , "function": lambda x: bool(x)},
                1: {"key": "next"    , "function": lambda x: bool(x)},
                2: {"key": "enter"   , "function": lambda x: bool(x)},
                3: {"key": "escape"  , "function": lambda x: bool(x)},
            }
        }),
    )

    def __init__(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        pygame.init()
        pygame.joystick.init()

        self._joystick = OrderedDict()

        for ndx in range(pygame.joystick.get_count()):
            try:
                joystick = pygame.joystick.Joystick(ndx)
                joystick.init()

                name = joystick.get_name()
                self._joystick[name] = {"instance": joystick, "profile": None, "status": {},}

                for keyword, profile in self.PROFILES:
                    if name.find(keyword) >= 0:
                        self._joystick[name]["profile"] = profile
                        break

                if self._joystick[name]["profile"] is None:
                    log("Found unsupported joystick #%d: %s" % (ndx, name))
                else:
                    log("Found supported joystick #%d: %s" % (ndx, name))

            except:
                error_exc("Unable to init joystick due to exceptions")


    def dump(self):
        if len(self._joystick) == 0:
            return None, None

        while True:
            has_axis   = False
            has_button = False
            has_hat    = False
            has_ball   = False

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return {"quit": True}, None

                if event.type == pygame.JOYAXISMOTION:
                    has_axis = True
                elif event.type == pygame.JOYBUTTONDOWN:
                    has_button = True
                elif event.type == pygame.JOYHATMOTION:
                    has_hat = True
                elif event.type == pygame.JOYBALLMOTION:
                    has_ball = True

            if has_axis or has_button or has_hat or has_ball:
                result        = {}
                active_name   = None
                active_status = {}

                for name in self._joystick:
                    joystick     = self._joystick[name]["instance"]
                    profile      = self._joystick[name]["profile" ]
                    result[name] = {"axis": {}, "button": {}, "ball": {}, "hat": {}}
                    status       = {}

                    for ndx in range(joystick.get_numaxes()):
                        result[name]["axis"][ndx] = joystick.get_axis(ndx)

                    for ndx in range(joystick.get_numbuttons()):
                        result[name]["button"][ndx] = joystick.get_button(ndx)

                    for ndx in range(joystick.get_numballs()):
                        result[name]["ball"][ndx] = joystick.get_ball(ndx)

                    for ndx in range(joystick.get_numhats()):
                        result[name]["hat"][ndx] = joystick.get_hat(ndx)

                    if has_axis:
                        if "axis" not in status:
                            status["axis"] = {}

                        if profile is not None and "axis" in profile:
                            for ndx, mapping in profile["axis"].items():
                                status["axis"][mapping["key"]] = mapping["function"](joystick.get_axis(ndx))

                    if has_button:
                        if "button" not in status:
                            status["button"] = {}

                        if profile is not None and "button" in profile:
                            for ndx, mapping in profile["button"].items():
                                if mapping["function"](joystick.get_button(ndx)):
                                    status["button"][mapping["key"]] = True

                    if has_hat:
                        if "hat" not in status:
                            status["hat"] = {}

                        if profile is not None and "hat" in profile:
                            for ndx, mapping in profile["hat"].items():
                                status["hat"][mapping["key"]] = mapping["function"](joystick.get_button(ndx))

                    if has_ball:
                        if "ball" not in status:
                            status["ball"] = {}

                        if profile is not None and "ball" in profile:
                            for ndx, mapping in profile["ball"].items():
                                status["ball"][mapping["key"]] = mapping["function"](joystick.get_button(ndx))

                    if result[name] == self._joystick[name]["status"]:
                        continue

                    self._joystick[name]["status"] = result[name]
                    active_name   = name
                    active_status = status

                if active_name:
                    return result, active_name, active_status

            time.sleep(0.05)


    def poll(self, timeout = 3):
        if len(self._joystick) == 0:
            return None, None

        start = time.time()
        while True:
            has_axis   = False
            has_button = False
            has_hat    = False
            has_ball   = False

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None, {"quit": True}

                if event.type == pygame.JOYAXISMOTION:
                    has_axis = True
                elif event.type == pygame.JOYBUTTONDOWN or pygame.JOYBUTTONUP:
                    has_button = True
                elif event.type == pygame.JOYHATMOTION:
                    has_hat = True
                elif event.type == pygame.JOYBALLMOTION:
                    has_ball = True

            if has_axis or has_button or has_hat or has_ball:
                active_name   = None
                active_status = None
                unsupported   = 0

                for name in self._joystick:
                    joystick = self._joystick[name]["instance"]
                    profile  = self._joystick[name]["profile" ]
                    status   = {}

                    if profile is None:
                        unsupported += 1

                    if has_axis:
                        if "axis" not in status:
                            status["axis"] = {}

                        if profile is not None and "axis" in profile:
                            for ndx, mapping in profile["axis"].items():
                                status["axis"][mapping["key"]] = mapping["function"](joystick.get_axis(ndx))

                    if has_button:
                        if "button" not in status:
                            status["button"] = {}

                        if profile is not None and "button" in profile:
                            for ndx, mapping in profile["button"].items():
                                if mapping["function"](joystick.get_button(ndx)):
                                    status["button"][mapping["key"]] = True

                    if has_hat:
                        if "hat" not in status:
                            status["hat"] = {}

                        if profile is not None and "hat" in profile:
                            for ndx, mapping in profile["hat"].items():
                                status["hat"][mapping["key"]] = mapping["function"](joystick.get_button(ndx))

                    if has_ball:
                        if "ball" not in status:
                            status["ball"] = {}

                        if profile is not None and "ball" in profile:
                            for ndx, mapping in profile["ball"].items():
                                status["ball"][mapping["key"]] = mapping["function"](joystick.get_button(ndx))

                    if status == self._joystick[name]["status"]:
                        if ("button" not in status or len(status["button"]) == 0) and \
                           ("hat"    not in status or len(status["hat"   ]) == 0) and \
                           ("ball"   not in status or len(status["ball"  ]) == 0):
                            continue

                    self._joystick[name]["status"] = status
                    active_name   = name
                    active_status = status

                if active_name:
                    return active_name, active_status

                if unsupported > 0:
                    return None, {"unsupported": True}

            if timeout > 0 and time.time() - start >= timeout:
                return None, {}

            time.sleep(0.001)


    def wait_any_key(self, timeout = 3):
        while True:
            name, status = self.poll(timeout = 0)
            if len(status) == 0 or len(status.get("button", {})) == 0:
                break

        self.poll(timeout = timeout)


def run_parallelly(func, param_list):
    threads = []

    for i in range(len(param_list)):
        threads.append(threading.Thread(target = func, args = param_list[i]))
        threads[i].start()

    for i in range(len(param_list)):
        threads[i].join()


class TrendCarBaseConnection(object):
    def __init__(self):
        pass

    def start_autopilot(self, host):
        return False

    def stop_autopilot(self, host):
        return False

    def push_firmware(self, host, firmware, callback = None, context = None):
        return False

    def open(self, *args, **kwargs):
        return False

    def close(self):
        pass

    def drive(steering, throttle):
        pass


class TrendCarSSHConnection(TrendCarBaseConnection):
    def __init__(self):
        super(type(self), self).__init__()
        self._host   = None
        self._ssh    = None
        self._stdin  = None
        self._stdout = None
        self._stderr = None
        self._pkey   = paramiko.RSAKey.from_private_key(StringIO.StringIO(TrendCarSSHConnection.PRIVATE_KEY))


    def _control_autopilot(self, host, enabled):
        ssh = None
        try: 
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(host, 22, TrendCarSSHConnection.DEF_USER, TrendCarSSHConnection.DEF_PASSWD, pkey = self._pkey)
                log("Connected to %s", host)

                stdin, stdout, stderr = ssh.exec_command('trendcar-console -q')
                stdin.channel.send(b";")
                self._wait_input_idle(timeout = 2000, ssh = ssh, stdin = stdin, stdout = stdout, stderr = stderr)

                for tries in range(20):
                    stdin.channel.send(b"0~%d\t" % (int(enabled)))
                    self._wait_input_idle(timeout = 50, ssh = ssh, stdin = stdin, stdout = stdout, stderr = stderr)

                return True

            finally:
                if ssh:
                    ssh.close()
        except:
            error_exc("Exception occurred during controling autopilot")

        return False


    def start_autopilot(self, host):
        return self._control_autopilot(host, True)


    def stop_autopilot(self, host):
        return self._control_autopilot(host, False)


    def push_firmware(self, host, firmware, callback = None, context = None):
        ssh = None
        try: 
            def _progress_callback(transferred, total):
                if callback:
                    callback(host, context, transferred, total)

            try:
                os.system("ping -c 1 %s" % (host))
                log("Uploading %s to %s...", firmware, host)
                transport = paramiko.Transport((host, 22))
                transport.connect(username = TrendCarSSHConnection.DEF_USER, password = TrendCarSSHConnection.DEF_PASSWD, pkey = self._pkey)
                sftp = paramiko.SFTPClient.from_transport(transport)
                sftp.put(firmware, "trendcar.7z", callback = _progress_callback)
                sftp.close()
                transport.close()
                log("%s was uploaded to %s", firmware, host)

                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(host, 22, TrendCarSSHConnection.DEF_USER, TrendCarSSHConnection.DEF_PASSWD, pkey = self._pkey)
                log("Connected to %s", host)

                stdin, stdout, stderr = ssh.exec_command(r'trendcar-config --noui --update_with_file trendcar.7z; rm trendcar.7z; exit')
                self._wait_input_idle(timeout = 10 * 60 * 1000, ssh = ssh, stdin = stdin, stdout = stdout, stderr = stderr)

                if callback:
                    callback(host, context, 0, 0)

                return True

            finally:
                if ssh:
                    ssh.close()
                    ssh = None

        except paramiko.SSHException as e:
            log("Failed to push firmware. %s", str(e))

        except:
            error_exc("Exception occurred during controling autopilot")

        if callback:
            callback(host, context, -1, -1)

        return False


    def open(self, host, *args, **kwargs):
        self.close()

        if host is not None and self._host != host:
            self._host = host

        if self._host is None:
            return False

        try:
            self._ssh  = paramiko.SSHClient()
            self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh.connect(self._host, 22, TrendCarSSHConnection.DEF_USER, TrendCarSSHConnection.DEF_PASSWD, pkey = self._pkey)
            log("Connected to %s", self._host)

            self._stdin, self._stdout, self._stderr = self._ssh.exec_command('trendcar-console -q')

            self._stdin.channel.send(b";1~")
            self._wait_input_idle(2000)
            return self.drive(0.0, 0.0, try_reopen = False)

        except:
            error_exc("Failed to connect to %s", self._host)
            self.close()

        return False


    def close(self):
        if self._ssh:
            self.drive(0.0, 0.0, try_reopen = False)

            try:
                self._ssh.close()
            except:
                pass

            self._ssh    = None
            self._stdin  = None
            self._stdout = None
            self._stderr = None


    def drive(self, steering, throttle, try_reopen = True):
        debug("steering = %0.2f, throttle = %0.3f" % (steering, throttle))

        if not self._ssh or not self._stdin or not self._stdout or not self._stderr:
            if try_reopen:
                debug("No available connections")
            return False

        tries = 2
        while tries > 0:
            try:
                self._wait_input_idle(timeout = 1)
                self._stdin.channel.send("%0.2f%s" % (steering, "j" if steering < 0.0 else "l"))
                self._wait_input_idle(timeout = 1)
                self._stdin.channel.send("%0.3f%s" % (throttle, "k" if throttle < 0.0 else "i"))
                self._wait_input_idle(timeout = 50)
                return True

            except:
                if not try_reopen:
                    debug("Unable to send drive command")
                    raise

                tries -= 1
                if tries == 0:
                    debug("Unable to send drive command")
                    raise

                while tries > 0:
                    if self.open(None):
                        break
                    tries -= 1

        debug("Unable to send drive command")
        return False


    def _wait_input_idle(self, timeout = 1000, ssh = None, stdin = None, stdout = None, stderr = None):
        if ssh is None:
            ssh    = self._ssh
            stdin  = self._stdin
            stdout = self._stdout
            stderr = self._stderr

        if not ssh or not stdin or not stdout or not stderr:
            return

        max_idle_count_down = timeout
        idle_count_down     = max_idle_count_down

        try:
            while not stdout.channel.exit_status_ready() and idle_count_down > 0:
                if stderr.channel.recv_ready():
                    buf = stdout.channel.recv(1024)
                    sys.stderr.write(buf)
                    idle_count_down = max_idle_count_down
                    continue

                if stdout.channel.recv_ready():
                    buf = stdout.channel.recv(1024)
                    sys.stdout.write(buf)
                    sys.stdout.flush()
                    idle_count_down = max_idle_count_down
                    continue

                idle_count_down -= 1
                time.sleep(0.001)
        except:
            raise


    DEF_USER    = "pi"
    DEF_PASSWD  = "raspberry"
    PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----\n"""                                  \
                  """MIIEogIBAAKCAQEAxU8qY/nBkBoPEHcShBnco6yqiwr7HbX+c47hK4jc/axLZyTO\n""" \
                  """8vkUa7bi+VdeD8Xa8xAxR1cMnA9fbBmUn3+HMqDZ41Dzz+nhiOz7JgECGlhOgUXY\n""" \
                  """/yPjWQOoeQLvZpeZx4KUyLNHWOT4tAECpojdB/Pyaf90lECKC3VF5eXdH62/yxP6\n""" \
                  """ptylF2iDSJnfN/ZaT2G57YVMPNqIehHL/UQtVWAI2xm1O8ZQJsLaBlvzjHyxNQK9\n""" \
                  """M1qjFn67lvfShPqN07+iFhMCs15+4gxM1GwGF+B/66zhBKXYAnWAbNv6Uh5vqa+w\n""" \
                  """iZ92QbkwOOYy/XN35uXjyAUuUGmnD3mzfn6wFwIDAQABAoIBAHpUMrv5RQDKpzxW\n""" \
                  """FqzAPANeMf4yuK4a/781fnU3TYwZHka8k3Ig64A8y0w71p2A1daM24CXf8Hh5g9n\n""" \
                  """bLXWo0PIZk6BCiiFoMb75loRlfQve7y6SWcmIPY3RmSAZVz98OG5G/Wy8TE0BN3V\n""" \
                  """IoeNozwjCtCdCPJBcVTZSJTYhtf0ERNGn0pDPg8Bm2ZD3IL1TaNiUqhgjSTIgzQj\n""" \
                  """k5rt5mRki5p38vE56sBowI/s52Z8hCukSbkqGQ3PhIoXUn9rViTcyF4ZBZubJX9J\n""" \
                  """vrs1q0lpSURkM7kYxPNSNeLqxfd4K0PAfpEmc1nHSmpi8+y6a7T07LLzb3rE89T3\n""" \
                  """O3bQ6MECgYEA+apxmLIoZHEKr9mh5TKWR1GRQF2GHEwEYnGi/Bqp5ikeBWQ9ejyw\n""" \
                  """bbQKc6iEfDyo5qHYLWFgxROQTwdXmt62ZvinlU9CZlESgUF5tPmO3lTWuwmmk0mU\n""" \
                  """6GBdPd9u1KB729rRi0ykge17eQwJ5qfStxoPWssj6jPRIzcM3z6KVIUCgYEAylCr\n""" \
                  """vdYK8drWuqK84te/orz+28g6H+3gofI2aXlzgmH4OP/I12Q3Bmvxs+IQ+xiPbWCo\n""" \
                  """sDIFcjLckP4i/GH7ouXcpDiq/IZhjnjPFwre7c2x5hAo7iHPkyrLb+8N1BOH2KJ9\n""" \
                  """J376OGxEV6ZZj9OypMeXkg+t/YHt9T3RYbHW0usCgYBvdaJlMxRJUxYcT6KxOhZR\n""" \
                  """HJ8mBxq6Q02pzWWf+x9ie3TFn2y6x6FUOI559/+9ny8gV5y1FcYn9YX1YifAIjF4\n""" \
                  """YwYd6FaSaxtBzUNSgh9ALsv2kGZnVvA9ldfKqZdHIaZqDpSCBeNjhewbrD43VTED\n""" \
                  """QYUdWZddFWkGuarrd3Y2KQKBgBQQCefqaO1w+ShK6RZJtNxLh6593Z269jK5FUJC\n""" \
                  """Y/0DAB2O5/jMHFTLsY1YFrz/w4FiO3g1jaq0doD+YrPKd6zAxK+YWwRtwxDg1BCB\n""" \
                  """6HeGlWSuJ5Dt02rRrJjuCN4GDcui2WxoQCIGQoS6n1kO8kE69cHrQiLIlrNiLPhW\n""" \
                  """LWp/AoGAAJ5R9ppjfHc1xjlg1tehhaL7mYCwAKNAPOkrmhjdrT0j1KKseJKQuq7I\n""" \
                  """UZnX/Y92R3FQVU2XIHYqfNgN1mtlV6OsUPqNHN3JJgLP0hEIbOujG48xuufcoUPJ\n""" \
                  """RMAEZMwYYea1m2X4hgHOBeppQ2UE/dpNFmXe7+6zMMgmZQlPQsg=\n"""             \
                  """-----END RSA PRIVATE KEY-----\n"""


def install():
    try:
        os.chmod(__file__, 0o755)

        with open("/lib/systemd/system/trendcar-fpv.service", "w") as f:
            f.write("""[Unit]\n"""                                       \
                    """Description=Trend Car FPV Controller Service\n""" \
                    """After=network.target\n"""                         \
                    """\n"""                                             \
                    """[Service]\n"""                                    \
                    """ExecStart=%s\n"""                                 \
                    """ExecReload=/bin/kill -HUP \$MAINPID\n"""          \
                    """ExecStop=/bin/kill -HUP \$MAINPID\n"""            \
                    """Restart=on-failure\n"""                           \
                    """KillMode=process\n"""                             \
                    """\n"""                                             \
                    """[Install]\n"""                                    \
                    """WantedBy=multi-user.target\n"""                   \
                    """Alias=trendcar-fpv.service\n""" % (os.path.realpath(__file__)))

        os.system("systemctl enable trendcar-fpv")
        os.system("systemctl start trendcar-fpv")
        return 0
    except:
        error_exc("Exception occurred while installing the daemon")

    return 1


def uninstall():
    try:
        os.system("systemctl stop trendcar-fpv")
        os.system("systemctl disable trendcar-fpv")
        os.remove("/lib/systemd/system/trendcar-fpv.service")
        os.system("systemctl daemon-reload")
        return 0
    except:
        error_exc("Exception occurred while uninstalling the daemon")

    return 1


def dump_joystick():
    from pprint import pprint

    try:
        joystick = JoyStick()

        while True:
            result, name, status = joystick.dump()

            if result is None:
                log("No joystick found")
                return 1

            if result.get("quit", False):
                log("Quit")
                return 0

            os.system("clear")
            pprint(result)
            pprint(name)
            pprint(status)

    except KeyboardInterrupt:
        pass
    except:
        raise

    return 0


def load_hosts(filename):
    hosts = []
    names = []

    try:
        filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), filename)

        with open(filepath, "rb") as f:
            for row in csv.reader(f):
                if len(row) == 0:
                    continue
                hosts.append(row[0])

                if len(row) > 1:
                    names.append(row[1])
    except:
        error_exc("Error loading hosts")

    return hosts, names


def save_hosts(filename, hosts, names):
    try:
        filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), filename)
        tmpfile  = filepath + ".tmp"
        bakfile  = filepath + ".bak"

        with open(tmpfile, "wb") as f:
            csv_file = csv.writer(f)

            for i in range(len(hosts)):
                csv_file.writerow([hosts[i], names[i]])

        try:
            os.remove(bakfile)
        except:
            pass

        try:
            os.rename(filepath, bakfile)
        except:
            pass

        os.rename(tmpfile, filepath)

        try:
            os.remove(bakfile)
        except:
            pass

	os.system("sync; sync; sync")
	os.system("echo 3 > /proc/sys/vm/drop_caches")
        return True

    except:
        error_exc("Error saving hosts")

        try:
            os.rename(bakfile, filepath)
        except:
            pass

        try:
            os.remove(tmpfile)
        except:
            pass

    time.sleep(600)
    return False


def get_ipaddr(ifname = "wlan0"):
    import socket
    import fcntl
    import struct

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])


def main():
    hosts, names = load_hosts("trendcar-fpv-hosts.csv")

    try:
        connection  = TrendCarSSHConnection()
        joystick    = JoyStick()
        dashboard   = Dashboard()
        last_active = None

        dashboard.show_logo()

        while True:
            active, status = joystick.poll()

            if status is None:
                log("No joystick found")
                dashboard.show_message("No Joysticks")
                return 1

            if status.get("quit", False):
                log("Quit")
                return 0

            if status.get("unsupported", False):
                log("No supported joysticks")
                dashboard.show_message("Unknown Joystick")
                return 1

            if last_active != active:
                log("Active joystick: %s", active)
                last_active = active

            if "button" in status:
                if status["button"].get("enter", False) or status["button"].get("escape", False):
                    menu_stack = [0]
                    try:
                        ipv4_tuple = [int(x) for x in get_ipaddr().split(".")]
                    except:
                        ipv4_tuple = [0, 0, 0, 0]

                    while True:
                        menu_path   = menu_stack[:-1]
                        menu_cursor = menu_stack[-1]
                        menu_items  = []
                        menu_action = None

                        if menu_path == []:
                            menu_items = [
                                "Connect Car",      # 0
                                "Add Car",          # 1
                                "Remove Car",       # 2
                                "Stop Autopilot",   # 3
                                "Start Autopilot",  # 4
                                "Push Firmware",    # 5
                            ]
                        elif menu_path == [0]:      # Connect Car
                            menu_items = hosts
                        elif menu_path == [1]:      # Add Car
                            menu_items  = ipv4_tuple
                            menu_action = dashboard.edit_ipv4
                        elif menu_path == [2]:      # Remove Car
                            menu_items = hosts
                        elif menu_path == [3]:      # Stop Autopilot
                            menu_items = [
                                "All Cars",
                            ]
                            menu_items.extend(hosts)
                        elif menu_path == [4]:      # Start Autopilot
                            menu_items = [
                                "All Cars",
                            ]
                            menu_items.extend(hosts)
                        elif menu_path == [5]:      # Push Firmware
                            menu_items = [
                                "All Cars",
                            ]
                            menu_items.extend(hosts)

                        if menu_action is not None:
                            menu_action(menu_items, menu_cursor)
                        elif menu_items is not None:
                            dashboard.show_menu(menu_items, menu_cursor)

                        active, status = joystick.poll()

                        if last_active != active:
                            log("Active joystick: %s", active)
                            last_active = active

                        if "button" in status:
                            if status["button"].get("escape", False):
                                if menu_path == []:
                                    break
                                else: 
                                    menu_stack.pop()
                                continue

                            if status["button"].get("enter", False):
                                if menu_path == []:
                                    menu_stack.append(0)

                                elif menu_path == [0]:      # Connect Car
                                    if menu_cursor < len(hosts):
                                        dashboard.show_message("Connecting")

                                        if connection.open(hosts[menu_cursor]):
                                            dashboard.show_message("Connected")
                                        else:
                                            dashboard.show_message("Disconnected")

                                        joystick.wait_any_key(timeout = 3)
                                        break
                                    else:
                                        menu_stack.pop()

                                elif menu_path == [1]:      # Add Car
                                    hosts.append(".".join([str(i) for i in ipv4_tuple]))
                                    names.append("")
                                    save_hosts("trendcar-fpv-hosts.csv", hosts, names)
                                    menu_stack.pop()

                                elif menu_path == [2]:      # Remove Car
                                    if menu_cursor < len(hosts):
                                        del hosts[menu_cursor]
                                        del names[menu_cursor]
                                        save_hosts("trendcar-fpv-hosts.csv", hosts, names)
                                    else:
                                        menu_stack.pop()

                                elif menu_path == [3]:      # Stop Autopilot
                                    if menu_cursor == 0:
                                        dashboard.show_message("Stopping all")
                                        conn = TrendCarSSHConnection()
                                        run_parallelly(conn.stop_autopilot, [(x,) for x in hosts])
                                        del conn
                                        dashboard.show_message("Done")
                                        joystick.wait_any_key(timeout = 3)

                                    elif menu_cursor <= len(hosts):
                                        dashboard.show_message("Stopping")

                                        conn = TrendCarSSHConnection()
                                        if conn.stop_autopilot(hosts[menu_cursor - 1]):
                                            dashboard.show_message("Stopped")
                                        else:
                                            dashboard.show_message("Unsuccessful")

                                        del conn
                                        joystick.wait_any_key(timeout = 3)
                                    else:
                                        menu_stack.pop()

                                elif menu_path == [4]:      # Start Autopilot
                                    if menu_cursor == 0:
                                        dashboard.show_message("Starting all")
                                        conn = TrendCarSSHConnection()
                                        run_parallelly(conn.start_autopilot, [(x,) for x in hosts])
                                        del conn
                                        dashboard.show_message("Done")
                                        joystick.wait_any_key(timeout = 3)

                                    elif menu_cursor <= len(hosts):
                                        dashboard.show_message("Starting")

                                        conn = TrendCarSSHConnection()
                                        if conn.start_autopilot(hosts[menu_cursor - 1]):
                                            dashboard.show_message("Started")
                                        else:
                                            dashboard.show_message("Unsuccessful")

                                        del conn
                                        joystick.wait_any_key(timeout = 3)
                                    else:
                                        menu_stack.pop()

                                elif menu_path == [5]:      # Push Firmware
                                    firmware = glob(os.path.join(os.path.dirname(os.path.realpath(__file__)), "trendcar.*.7z"))
                                    firmware.sort(reverse = True)
                                    firmware = firmware[0]

                                    if menu_cursor == 0:
                                        dashboard.show_message("Pushing firmware")

                                        progress_context = {"overall_progress": 0, "threshold": 0, "total": len(hosts), "complete": set(), "error": set()}

                                        def progress_callback(host, context, transferred, total_bytes):
                                            progress = 0

                                            if total_bytes > 0:
                                                if transferred < total_bytes:
                                                    progress = 80.0 * transferred / total_bytes
                                                    context["overall_progress"] = max(context["overall_progress"], progress)
                                                    progress = context["overall_progress"]
                                            elif total_bytes == 0:
                                                context["complete"].add(host)
                                                progress = 80.0 + 20.0 * len(context["complete"]) / (context["total"] - len(context["error"]))
                                                context["overall_progress"] = max(context["overall_progress"], progress)
                                                progress = context["overall_progress"]
                                            else:
                                                context["error"].add(host)

                                            if progress >= context["threshold"]:
                                                context["threshold"] = int(progress) + 1
                                                dashboard.show_progress(progress)

                                        conn = TrendCarSSHConnection()
                                        run_parallelly(conn.push_firmware, [(x, firmware, progress_callback, progress_context) for x in hosts])
                                        del conn

                                        nr_complete = len(progress_context["complete"])
                                        nr_errors   = len(progress_context["error"   ])

                                        if nr_errors == 0:
                                            dashboard.show_message("All succeeded")
                                        elif nr_complete == 0:
                                            dashboard.show_message("All failed")
                                        else:
                                            dashboard.show_message("%d of %d succeeded" % (nr_complete, len(hosts)))

                                        joystick.wait_any_key(timeout = 3)
                                    elif menu_cursor <= len(hosts):
                                        dashboard.show_message("Pushing firmware")
                                        progress_context = {"threshold": 0}

                                        def progress_callback(host, context, transferred, total_bytes):
                                            if total_bytes > 0:
                                                if transferred < total_bytes:
                                                    progress = 100.0 * transferred / total_bytes
                                                    if progress >= context["threshold"]:
                                                        context["threshold"] = int(progress) + 1
                                                        dashboard.show_progress(progress)
                                                else:
                                                    dashboard.show_message("Installing")
                                            elif total_bytes == 0:
                                                dashboard.show_message("Complete")
                                            else:
                                                dashboard.show_message("Incomplete")

                                        conn = TrendCarSSHConnection()
                                        if conn.push_firmware(hosts[menu_cursor - 1], firmware, progress_callback, progress_context):
                                            dashboard.show_message("Successful")
                                        else:
                                            dashboard.show_message("Unsuccessful")

                                        del conn
                                        joystick.wait_any_key(timeout = 3)
                                    else:
                                        menu_stack.pop()

                                continue

                            if not menu_items:
                                continue

                            if status["button"].get("next", False):
                                menu_stack[-1] = (menu_stack[-1] + 1) % len(menu_items)
                            elif status["button"].get("prev", False):
                                menu_stack[-1] = len(menu_items) - 1 if menu_stack[-1] == 0 else menu_stack[-1] - 1

                        if "axis" in status:
                            if menu_path == [1]:
                                steering = status["axis"].get("steering", None)

                                if steering is not None:
                                    ipv4_tuple[menu_cursor] = (ipv4_tuple[menu_cursor] + int(steering / 90.0 * 5)) % 255
                                    continue

                                throttle = status["axis"].get("throttle", None)
                                brake    = status["axis"].get("brake"   , None)

                                if throttle is not None or brake is not None:
                                    if throttle is None:
                                        throttle = 0.0
                                    if brake is not None:
                                        throttle -= brake

                                    ipv4_tuple[menu_cursor] = (ipv4_tuple[menu_cursor] + int(throttle * 10)) % 255
                                    continue


                dashboard.clear_menu()
                dashboard.show_logo()
                continue

            steering = 0.0
            throttle = 0.0

            if "axis" in status:
                steering = status["axis"].get("steering", 0.0)
                throttle = round(status["axis"].get("throttle", 0.0) - status["axis"].get("brake", 0.0), 1)

            connection.drive(steering, throttle)

            if throttle == 0.0:
                connection.drive(0.0, 0.0)

            if steering == 0.0 and throttle == 0.0:
                dashboard.show_logo()
            else:
                dashboard.show_steering(steering)
                dashboard.show_throttle(throttle)


    except KeyboardInterrupt:
        pass
    except:
        error_exc("Unexpected exception occurred")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", action="store_true", help="Dump joystick status only")
    parser.add_argument("--install", action="store_true", help="Register daemon")
    parser.add_argument("--uninstall", action="store_true", help="Unregister daemon")
    args = parser.parse_args()

    if args.install:
        sys.exit(install())

    if args.uninstall:
        sys.exit(uninstall())

    if args.dump:
        sys.exit(dump_joystick())

    sys.exit(main())

