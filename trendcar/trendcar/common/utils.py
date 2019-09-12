
def set_thread_name(name):
    import sys, ctypes

    if sys.platform.startswith("linux"):
        libc           = ctypes.cdll.LoadLibrary('libc.so.6')
        name_buf       = ctypes.create_string_buffer(len(name) + 1)
        name_buf.value = name.encode('iso8859-1')
        libc.prctl(15, ctypes.byref(name_buf), 0, 0, 0)


def get_stdin_binary_mode():
    import sys

    if sys.version > '3':
        return sys.stdin.buffer

    if sys.platform == "win32":
        import os, msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)

    return sys.stdin


def get_stdout_binary_mode():
    import sys

    if sys.version > '3':
        return sys.stdout.buffer

    if sys.platform == "win32":
        import os, msvcrt
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

    return sys.stdout


_ipv4_tcp_ports = set()

def allow_incoming_ipv4_tcp(port_spec):
    global _ipv4_tcp_ports
    _ipv4_tcp_ports.add(port_spec)


def revoke_incoming_ipv4_tcp(port_spec):
    global _ipv4_tcp_ports
    _ipv4_tcp_ports.remove(port_spec)


def reset_firewall():
    global _ipv4_tcp_ports
    _ipv4_tcp_ports.clear()
    commit_firewall()


def commit_firewall():
    import os
    from common import hwinfo
    global _ipv4_tcp_ports

    if not hwinfo.is_running_in_pi():
        return

    os.system("sudo iptables -F IN_TRENDCAR")

    for port_spec in _ipv4_tcp_ports:
        if type(port_spec) is int:
            os.system("sudo iptables -A IN_TRENDCAR -p tcp --dport %d --syn -j ACCEPT" % (port_spec,))
        elif type(port_spec) in (list, tuple) and len(port_spec) == 2:
            os.system("sudo iptables -A IN_TRENDCAR -p tcp -m multiport --dports %d:%d --syn -j ACCEPT" % port_spec)
        else:
            warn("commit_firewall: unsupported port spec %s", repr(port_spec))

    os.system("sudo iptables -A IN_TRENDCAR -j RETURN")

