#!/usr/bin/python

from __future__ import print_function

try:
    import configparser
    _older_configparser = False
except:
    import ConfigParser as configparser
    _older_configparser = True


_config      = None
_base_config = None
_user_config = None


def load(config_file, user_defined = False):
    global _config, _base_config, _user_config

    if user_defined:
        _user_config = configparser.ConfigParser()

        try:
            _user_config.read(config_file)
        except:
            return False
    else:
        _base_config = configparser.ConfigParser()

        try:
            _base_config.read(config_file)
        except:
            return False

    _config = configparser.ConfigParser()

    if _base_config is not None:
        for k, v in _base_config.items("DEFAULT", True):
            _config.set("DEFAULT", k, v)

        for s in _base_config.sections():
            if not _config.has_section(s):
                _config.add_section(s)

            for k, v in _base_config.items(s, True):
                _config.set(s, k, v)

    if _user_config is not None:
        for k, v in _user_config.items("DEFAULT", True):
            if k in ("version", "release_date", "user_addon_folder"):
                continue
            _config.set("DEFAULT", k, v)

        for s in _user_config.sections():
            if not _config.has_section(s):
                _config.add_section(s)

            for k, v in _user_config.items(s, True):
                _config.set(s, k, v)

    return True


def save(config_file, user_defined = False):
    global _user_config, _base_config

    _cfg = _user_config if user_defined else _base_config

    if _cfg is None:
        return False

    config_file_tmp = "%s.tmp" % (config_file)
    config_file_bak = "%s.bak" % (config_file)

    try:
        with open(config_file_tmp, "w") as fp:
            _cfg.write(fp)

            try:
                os.remove(config_file_bak)
            except:
                pass

            try:
                os.rename(config_file, config_file_bak)
                os.rename(config_file_tmp, config_file)

                try:
                    os.chmod(config_file, 0o666)
                except:
                    pass

                try:
                    os.remove(config_file_bak)
                except:
                    pass

                return True
            except:
                try:
                    os.rename(config_file_bak, config_file)
                except:
                    pass
    except:
        try:
            os.remove(config_file_tmp)
        except:
            pass

    return False


def get(section, key, def_value = None, base_config_only = False):
    global _config, _base_config, _older_configparser
    import os

    _cfg = _base_config if base_config_only else _config

    if _cfg is None or not _cfg.has_option(section, key):
        return def_value

    if _older_configparser:
        try:
            return _cfg.get(section, key, False, os.environ)
        except TypeError:
            _older_configparser = False
            
    return _cfg.get(section, key, vars=os.environ)


def getint(section, key, def_value = 0, base_config_only = False):
    value = get(section, key, None, base_config_only = base_config_only)

    if value is None:
        return def_value

    return int(value)


def getbool(section, key, def_value = False, base_config_only = False):
    value = get(section, key, None, base_config_only = base_config_only)

    if value is None:
        return def_value

    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    return bool(float(value))


def getfloat(section, key, def_value = 0.0, base_config_only = False):
    value = get(section, key, None, base_config_only = base_config_only)

    if value is None:
        return def_value

    return float(value)


def set(section, key, value, user_defined = False):
    global _config, _base_config, _user_config
    if user_defined:
        if _user_config is None:
            _user_config = configparser.ConfigParser()

        _user_config.set(section, key, str(value))
    else:
        _base_config.set(section, key, str(value))

    _config.set(section, key, str(value))
    return True


if __name__ == "__main__":
    import os
    import sys

    if len(sys.argv) < 5:
        print("%s <config_file> get <section> <key>" % (sys.argv[0]))
        print("%s <config_file> set <section> <key> <value>" % (sys.argv[0]))
        sys.exit(1)

    config_file = sys.argv[1]
    action      = sys.argv[2]
    section     = sys.argv[3]
    key         = sys.argv[4]

    if not os.path.exists(config_file):
        print("Error: %s not found." % (config_file))
        sys.exit(2)

    if not load(config_file):
        print("Error: Unable to load %s." % (config_file))
        sys.exit(3)

    _user_config_file = None
    _user_addon_folder = get("DEFAULT", "user_addon_folder")
    if not _user_addon_folder or not os.path.exists(_user_addon_folder):
        if os.path.expanduser("~pi") != "~pi":
            _homedir = os.path.expanduser("~pi")
        else:
            _homedir = os.path.expanduser("~") or os.getenv("HOME")

        if _homedir and os.path.exists(_homedir):
            _user_addon_folder = os.path.join(_homedir, "trendcar")
            if not os.path.exists(_user_addon_folder):
                _user_addon_folder = None

    if _user_addon_folder:
        _user_config_file = os.path.join(_user_addon_folder, "userconfig.ini")
        if os.path.exists(_user_config_file):
            load(_user_config_file, user_defined = True)

    if action == "get":
        if len(sys.argv) != 5:
            print("Error: Too many arguments")
            sys.exit(4)

        sys.stdout.write(get(section, key, ""))
        sys.stdout.flush()
        sys.exit(0)

    if action in ("set", "setuser"):
        if len(sys.argv) < 6:
            print("Error: Too few arguments")
            sys.exit(5)

        if len(sys.argv) > 6:
            print("Error: Too many arguments")
            sys.exit(6)

        user_defined = (action == "setuser")
        value = sys.argv[5]

        if not set(section, key, value, user_defined = user_defined):
            print("Error: Unable to set %s.%s = %s%s" % (section, key, value, " as user defined settings" if user_defined else ""))
            sys.exit(7)

        if not save(_user_config_file if user_defined else config_file, user_defined = user_defined):
            print("Error: Unable to update %s%s" % (_user_config_file if user_defined else config_file, " as user defined settings" if user_defined else ""))
            sys.exit(8)

        sys.exit(0)

    print("Error: unknown command %s" % (action))
    sys.exit(9)

