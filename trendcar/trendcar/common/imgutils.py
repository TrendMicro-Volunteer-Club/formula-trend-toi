from common.cv2compat import *
import numpy as np

def show_image(img, name = "image", scale = 1.0):
    if scale and scale != 1.0:
        img = cv2.resize(img, newsize, interpolation=cv2.INTER_CUBIC) 

    cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
    cv2.imshow(name, img)
    cv2.waitKey(1)


def save_image(folder, img, prefix = "img", suffix = ""):
    from datetime import datetime
    filename = "%s-%s%s.jpg" % (prefix, datetime.now().strftime('%Y%m%d-%H%M%S-%f'), suffix)
    cv2.imwrite(os.path.join(folder, filename), img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])


def rad2deg(radius):
    return radius / np.pi * 180.0


def deg2rad(degree):
    return degree / 180.0 * np.pi


def bgr2rgb(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def rgb2bgr(img):
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def split_image_by_ratios(img, ratios):
    if ratios and len(ratios) > 1:
        result = []

        for i in range(len(ratios) - 1):
            section = slice(*(int(x * img.shape[0]) for x in ratios[i: i + 1]))
            result.append(img[section, :, :])

        return result
    return [img]


def flatten_rgb(img):
    b, g, r = cv2.split(img)
    b_filter = (b == np.maximum(np.maximum(r, g), b)) & (b >= 120) & (r < 150) & (g < 150)
    g_filter = (g == np.maximum(np.maximum(r, g), b)) & (g >= 120) & (r < 150) & (b < 150)
    r_filter = (r == np.maximum(np.maximum(r, g), b)) & (r >= 120) & (g < 150) & (b < 150)
    y_filter = ((b >= 128) & (g >= 128) & (r < 100))

    b[y_filter], g[y_filter] = 255, 255
    r[np.invert(y_filter)] = 0

    b[b_filter], b[np.invert(b_filter)] = 255, 0
    r[r_filter], r[np.invert(r_filter)] = 255, 0
    g[g_filter], g[np.invert(g_filter)] = 255, 0

    flattened = cv2.merge((b, g, r))
    return flattened


def find_lines(img):
    grayed      = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred     = cv2.GaussianBlur(grayed, (3, 3), 0)
    #edged      = cv2.Canny(blurred, 0, 150)

    sobel_x     = cv2.Sobel(blurred, cv2.CV_16S, 1, 0)
    sobel_y     = cv2.Sobel(blurred, cv2.CV_16S, 0, 1)
    sobel_abs_x = cv2.convertScaleAbs(sobel_x)
    sobel_abs_y = cv2.convertScaleAbs(sobel_y)
    edged       = cv2.addWeighted(sobel_abs_x, 0.5, sobel_abs_y, 0.5, 0)

    lines       = cv2.HoughLinesP(edged, 1, np.pi / 180, 10, 5, 5)
    return lines


