from common.stuff       import *
from driver.textconsole import TextConsole
from driver.webconsole  import WebConsole
from brains             import *

import os
import sys
import argparse
import threading


_BASEDIR = os.path.dirname(os.path.realpath(__file__))
config.load(os.path.join(_BASEDIR, "config.ini"))
setloglevel(config.get("DEFAULT", "log_level", "DEBUG").strip())
setlogaggr(config.get("DEFAULT", "log_aggregation_enabled", "True").strip())


class TrendCar(object):
    user_addon_folder = None

    @staticmethod
    def init_user_addon_folder():
        _user_addon_folder = config.get("DEFAULT", "user_addon_folder")
        _user_config       = None

        def _chown(username, path):
            if username and os.getuid() == 0:
                import pwd
                pw = pwd.getpwnam(username)
                os.chown(path, pw.pw_uid, pw.pw_gid)

        if os.path.expanduser("~pi") != "~pi":
            _username = "pi"
            _homedir  = os.path.expanduser("~pi")
        else:
            _username = os.getenv("USER")
            _homedir  = os.path.expanduser("~") or os.getenv("HOME")

        if not _user_addon_folder and _homedir and os.path.exists(_homedir):
            _user_addon_folder = os.path.join(_homedir, "trendcar")

        if not _user_addon_folder:
            return False

        try:
            if os.path.exists(_user_addon_folder):
                os.chmod(_user_addon_folder, 0o777)
            else:
                os.makedirs(_user_addon_folder, 0o777)

                try:
                    _pilot_py_sample = os.path.join(_BASEDIR, "brains", "pilot.py.sample")
                    _pilot_py        = os.path.join(_user_addon_folder, "pilot.py")

                    import shutil
                    shutil.copy2(_pilot_py_sample, _pilot_py)
                    _chown(_username, _pilot_py)
                except:
                    pass

            try:
                _chown(_username, _user_addon_folder)
            except:
                warn_exc("Unable to initialize user addon folder: %s", _user_addon_folder)
        except:
            warn_exc("Unable to initialize user addon folder: %s", _user_addon_folder)

        _user_config = os.path.join(_user_addon_folder, "userconfig.ini")

        if not os.path.exists(_user_config):
            try:
                with open(_user_config, "w") as ini:
                    ini.write("[DEFAULT]\n")

                os.chmod(_user_config, 0o666)
                info("Created default user config %s", _user_config)

                try:
                    _chown(_username, _user_config)
                except:
                    warn_exc("Unable to initialize user config file: %s", _user_config)
            except:
                warn_exc("Unable to initialize user config file: %s", _user_config)

        config.load(_user_config, user_defined = True)
        info("Loaded user config %s", _user_config)
        setloglevel(config.get("DEFAULT", "log_level", "DEBUG").strip())
        setlogaggr(config.get("DEFAULT", "log_aggregation_enabled", "True").strip())

        if _user_addon_folder not in sys.path:
            sys.path.append(_user_addon_folder)
            info("Added user-addon folder %s to python module search paths", _user_addon_folder)

        sys.path.append(_user_addon_folder)
        TrendCar.user_addon_folder = _user_addon_folder
        return True


    @staticmethod
    def load_user_addon_folder():
        if not TrendCar.user_addon_folder:
            return False

        import imp
        from glob import glob

        for py in glob(os.path.join(TrendCar.user_addon_folder, "*.py")):
            name = os.path.splitext(os.path.basename(py))[0]

            if name == "__init__.py":
                continue

            if name in sys.modules:
                if sys.modules[name].__file__.startswith(py):
                    info("User-Addon: %s already loaded", name)
                else:
                    error("User-Addon: Failed to load %s due to collision in module names: %s, %s" % (name, py, sys.modules[name].__file__))
                continue

            try:
                fp, filename, params = imp.find_module(name)

                try:
                    if filename != py:
                        error("User-Addon: Failed to load %s due to collision in module names: %s, %s" % (name, py, filename))
                        continue

                    imp.load_module(name, fp, filename, params)
                    info("User-Addon: %s loaded from %s" % (name, filename))

                finally:
                    if fp:
                        fp.close()

            except:
                error_exc("User-Addon: Failed to load %s due to exceptions" % (name))
                continue

        return True


    @staticmethod
    def start_daemon(webconsole_embedded = False, launch_simulator_only = False):
        set_thread_name("trendcar-daemon")

        def _preferred_control_model():
            if launch_simulator_only:
                return Control.launch("TrendCarSimulatorModel", ignore_platform_check = True)

            return Control.auto_detect()

        with _preferred_control_model() as control:
            if control is None:
                error("No car controls could be initiated")
                return False

            return TrendCar()._daemon(control, webconsole_embedded = webconsole_embedded)


    def _daemon(self, control, webconsole_embedded = False):
        info("Starting TrendCar daemon...")

        self.load_user_addon_folder()

        if config.getbool("TEXTCONSOLE", "enabled"):
            TextConsole.start(control)

        if webconsole_embedded:
            WebConsole.start(control)

        AutoPilot.start(control)
        commit_firewall()

        try:
            while True:
                display_window()

        except KeyboardInterrupt:
            pass
        except:
            error_exc("Exception occurred")

        AutoPilot.stop()

        if webconsole_embedded:
            WebConsole.stop()

        if config.getbool("TEXTCONSOLE", "enabled"):
            TextConsole.stop()

        reset_firewall()
        info("TrendCar daemon stopped")


    @staticmethod
    def console(cmd, script, interactive, quiet):
        set_thread_name("trendcar-console")
        return TextConsole.console(cmd, script, interactive, quiet)


    @staticmethod
    def self_check():
        set_self_check(True)
        setloglevel(LOG_QUIET)

        with Control.auto_detect(quiet = True) as control:
            if control is None:
                return False
            return True


    @staticmethod
    def test_wheel(param):
        try:
            method, wheel, seconds = param.split(",")
            method  = method.strip().lower()
            wheel   = wheel.strip().lower().replace("-", "").replace("_", "")
            seconds = int(seconds)

            if seconds <= 0:
                error("Duration out of range: %s", param)

            import car.model
            model = car.model.get_model("TrendCarModel")

            if model is None:
                error("TrendCarModel not found")
                return False

            if not model.begin(skip_camera = True):
                error("Unable to begin TrendCarModel")
                return False

            motors_mapping = {
                "leftfront" : model.FRONT_LEFT_MOTOR,
                "frontleft" : model.FRONT_LEFT_MOTOR,
                "leftrear"  : model.REAR_LEFT_MOTOR,
                "rearleft"  : model.REAR_LEFT_MOTOR,
                "rightfront": model.FRONT_RIGHT_MOTOR,
                "frontright": model.FRONT_RIGHT_MOTOR,
                "rightrear" : model.REAR_RIGHT_MOTOR,
                "rearright" : model.REAR_RIGHT_MOTOR,
                "all":        model.ALL_MOTORS,
            }

            if wheel not in motors_mapping:
                error("Unknown wheel: %s", param)
                return False

            def _wait_to_complete():
                start   = monotonic()
                elapsed = 0
                counter = seconds

                while elapsed < seconds:
                    sys.stdout.write("\rWaiting for test to complete...%d        " % (counter))
                    sys.stdout.flush()
                    time.sleep(1)
                    elapsed = monotonic() - start
                    counter -= 1

                sys.stdout.write("\rWaiting for test to complete...done.     \n")
                sys.stdout.flush()

            if method == "forward":
                print("Driving %s forwards..." % (motors_mapping[wheel].lower().replace("_", " ")))
                model.control_motors({motors_mapping[wheel]: 1.0})
                _wait_to_complete()
                model.control_motors()

            elif method == "backward":
                print("Driving %s backwards..." % (motors_mapping[wheel].lower().replace("_", " ")))
                model.control_motors({motors_mapping[wheel]: -1.0})
                _wait_to_complete()
                model.control_motors()

            elif method == "switch":
                start     = monotonic()
                elapsed   = 0
                counter   = seconds
                direction = 1.0

                print("Driving %s forwards and backwards..." % (motors_mapping[wheel].lower().replace("_", " ")))
                while elapsed < seconds:
                    model.control_motors({motors_mapping[wheel]: direction})
                    sys.stdout.write("\rWaiting for test to complete...%d        " % (counter))
                    sys.stdout.flush()
                    time.sleep(1)
                    elapsed   = monotonic() - start
                    direction = -direction
                    counter -= 1

                model.control_motors()
                sys.stdout.write("\rWaiting for test to complete...done.     \n")
                sys.stdout.flush()

            else:
                error("Unknown method: %s", param)

            return True
        except:
            error_exc("Exception occurred")
            return False


if __name__ == "__main__":
    def get_argument_parser():
        parser = argparse.ArgumentParser()

        if len(sys.argv) > 1:
            if sys.argv[1] == "--cli":
                parser.add_argument("--cli"        , action="store_true", help="Start TrendCar cli mode")
                parser.add_argument("--self-check" , action="store_true", help="Run self-check procedure. trendcar-daemon should be stopped first.")
                parser.add_argument("--test-wheel" , type=str           , help="Test the wheel(s): <method,wheel,seconds>, where method={forward, backward, switch}, wheel={left-front, left-rear, right-front, right-rear, all}")
                parser.add_argument("--loglevel"   , type=str           , help="Set log level: DEBUG, INFO, WARN, ERROR")
                parser.add_argument("--logaggr"    , type=str           , help="Enable log aggregation: True, False")
                return parser

            if sys.argv[1] == "--console":
                parser.add_argument("--console"    , action="store_true", help="Start TrendCar text console")
                parser.add_argument("--cmd"        , type=str,            help="Send command string to text console")
                parser.add_argument("--script"     , type=str,            help="Send script to text console")
                parser.add_argument("--interactive", action="store_true", help="Enter interactive mode of text console if --cmd is specified")
                parser.add_argument("--quiet"      , action="store_true", help="Mute any output in the console")
                parser.add_argument("--loglevel"   , type=str           , help="Set log level: DEBUG, INFO, WARN, ERROR")
                parser.add_argument("--logaggr"    , type=str           , help="Enable log aggregation: True, False")
                return parser

            if sys.argv[1] == "--daemon":
                parser.add_argument("--daemon"     , action="store_true", help="Start TrendCar daemon")
                parser.add_argument("--webconsole" , action="store_true", help="Start web console in either daemon or standalone mode")
                parser.add_argument("--simulator"  , action="store_true", help="Start the simulator model disregarding the hosting environment")
                parser.add_argument("--loglevel"   , type=str           , help="Set log level: DEBUG, INFO, WARN, ERROR")
                parser.add_argument("--logaggr"    , type=str           , help="Enable log aggregation: True, False")
                return parser

        parser.add_argument("--cli"        , action="store_true", help="Start TrendCar CLI")
        parser.add_argument("--console"    , action="store_true", help="Start TrendCar text console")
        parser.add_argument("--daemon"     , action="store_true", help="Start TrendCar daemon")
        return parser

    parser = get_argument_parser()
    args = parser.parse_args()

    if args.loglevel is not None:
        setloglevel(args.loglevel)

    TrendCar.init_user_addon_folder()

    if args.loglevel is not None:
        setloglevel(args.loglevel)

    if args.logaggr is not None:
        setlogaggr(args.logaggr)

    if hasattr(args, "console") and args.console:
        sys.exit(TrendCar.console(args.cmd, args.script, args.interactive, args.quiet))

    if hasattr(args, "cli") and args.cli:
        if args.self_check:
            ret = 0 if TrendCar.self_check() else 1
            sys.exit(ret)

        if args.test_wheel is not None:
            ret = 0 if TrendCar.test_wheel(args.test_wheel) else 1
            sys.exit(ret)

    if hasattr(args, "daemon") and args.daemon:
        if config.getbool("WEBCONSOLE", "enabled"):
            args.webconsole = True

        TrendCar.start_daemon(webconsole_embedded = args.webconsole, launch_simulator_only = args.simulator)
        sys.exit(0)

    parser.print_help()
    sys.exit(1)

