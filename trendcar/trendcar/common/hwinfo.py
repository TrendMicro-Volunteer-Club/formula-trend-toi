import os

def is_running_in_pi():
    return os.path.exists("/sys/firmware/devicetree/base/model")

def get_pi_version():
    try:
        with open("/sys/firmware/devicetree/base/model", "r") as f:
            return f.read().strip()
    except:
        try:
            import RPi.GPIO as GPIO
            return GPIO.RPI_INFO["TYPE"]
        except:
            pass

    return None


if __name__ == "__main__":
    print(get_pi_version())

# vim: set sw=4 ts=4 et:
