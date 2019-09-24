from common.stuff  import *
from common.pid    import PID
from common        import imgutils

import math
import sys

@AutoPilot.register
class TrendCarPilot(AutoPilot):
    _track_view_range = (0.5, 0.8)
    yellow_light_range = [(20, 100, 100),(40, 255, 255)]
    green_light_range = [(40, 100, 100),(80, 255, 255)]


    def __init__(self):
        self._inverse = 0


    @AutoPilot.priority_normal
    def on_inquiry_drive(self, dashboard, last_result):
        if not self.get_autodrive_started():
            return None

        if self._inverse > 0 or self._detect_inverse(dashboard) == True:
            self._inverse -= 1
            return {"steering": 90.0, "throttle": -0.5}

        steering = self._find_steering_angle_by_color(dashboard)
        if steering == -100.0:
            return {"steering": 5.0, "throttle": -0.3}


        have_yellow_light = self._light_check(dashboard,self.yellow_light_range)

        have_green_light = self._light_check(dashboard,self.green_light_range)

        info("###  light detection:" +str(have_green_light) +","+ str(have_yellow_light) +"\n")
        #info(green_light)

        if have_yellow_light:
            steering = 0.0
            throttle = 0.0
        elif have_green_light:
            throttle = (0.7 - min(abs(float(steering) / 50.0), 0.5)) / 2.0
        else:
            throttle = 0.7 - min(abs(float(steering) / 50.0), 0.5)

        return {"steering": steering, "throttle": throttle}


    def _find_max_len(self, h_list):
        check_value     = 0
        side_region     = 1
        max_arrow_count = -1
        max_arrow_len   = []
        max_arrow_idx   = []
        arrow_len       = 0
        update_flag     = False
        '''
        if np.array_equal(h_list[0: side_region], side_region*[255]) == True and np.array_equal(h_list[-side_region:], side_region*[255]) == True:
            pass
        else:
            return max_arrow_len, max_arrow_idx
        '''
        check_list      = h_list[side_region:-side_region]
        for i in range(len(check_list)):
            if check_list[i]==check_value:
                arrow_len += 1
                if arrow_len > 20:
                    if update_flag == False:
                        max_arrow_count += 1
                        update_flag = True
                    if len(max_arrow_len) == max_arrow_count:
                        max_arrow_len.append(arrow_len)
                        max_arrow_idx.append(i)
                    else:
                        max_arrow_len[max_arrow_count] = arrow_len
                        max_arrow_idx[max_arrow_count] = i
            else:
                update_flag = False
                arrow_len = 0

        return max_arrow_len, max_arrow_idx


    def _detect_inverse(self, dashboard):
        inv_count             = 30
        frame                 = dashboard["frame"]
        img_height            = frame.shape[0]

        h_line                = self._flatten_rgb(frame[img_height-25:img_height,:,:])
        h_line_0              = h_line[0,:,2]
        h_line_1              = h_line[20,:,2]
        h_line_2              = h_line[22,:,2]
        l_line_0, i_line_0    = self._find_max_len(h_line_0)
        l_line_1, i_line_1    = self._find_max_len(h_line_1)
        l_line_2, i_line_2    = self._find_max_len(h_line_2)

        if len(l_line_0) == 2 and l_line_0[0] > 50 and l_line_0[1] > 50:
            if len(l_line_1) == 1 and len(l_line_2) == 1:
                if i_line_1[0] > i_line_0[0] and i_line_1[0] < i_line_0[1]:
                    sys.stderr.write("###  candidate\n")
                    sys.stderr.write('0: ' + str(l_line_0) + "\n")
                    sys.stderr.write('1: ' + str(l_line_1) + "\n")
                    sys.stderr.write('2: ' + str(l_line_2) + "\n")


            if len(l_line_1) == 1 and l_line_1[0] > 65 and l_line_1[0]<180:
                if len(l_line_2) == 1 and l_line_2[0] > 55 and l_line_2[0]<180:
                    if (l_line_1[0] - l_line_2[0]) > 8:
                        if i_line_1[0] > i_line_0[0] and i_line_1[0] < i_line_0[1]:
                            self._inverse = inv_count
                            sys.stderr.write("###inversei\n")
                            sys.stderr.write(str(l_line_0) + "\n")
                            sys.stderr.write(str(l_line_1) + "\n")
                            sys.stderr.write(str(l_line_2) + "\n")
                            self._inverse = inv_count
                            return True

        return False

    import cv2

    def _light_check(self,dashboard,color_range):
        img = dashboard["frame"][0:100, 0:320]
        hava_light = False
        img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(img_hsv,color_range[0],color_range[1] )
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 50:
                #x, y, w, h = cv2.boundingRect(cnt)
                hava_light = True
        return hava_light


    def _find_steering_angle_by_color(self, dashboard):
        if "frame" not in dashboard:
            return -100.0   # special case

        frame             = dashboard["frame"]
        img_height        = frame.shape[0]
        img_width         = frame.shape[1]
        camera_x          = img_width // 2

        track_view_slice  = slice(*(int(x * img_height) for x in self._track_view_range))
        track_view        = self._flatten_rgb(frame[track_view_slice, :, :])

        track_view_gray   = cv2.cvtColor(track_view, cv2.COLOR_BGR2GRAY)
        tracks            = map(lambda x: len(x[x > 20]), [track_view_gray])
        tracks_seen       = filter(lambda y: y > 200, tracks)

        if len(list(tracks_seen)) == 0:
            show_image("frame", frame)             # display image to opencv window
            show_image("track_view", track_view)   # display image to opencv window

            # show track image to webconsole
            dashboard["track_view"     ] = track_view
            dashboard["track_view_info"] = (track_view_slice.start, track_view_slice.stop, None)
            return -100.0   # special case

        _y, _x  = np.where(track_view_gray == 76)
        if len(_x) == 0:
            return -100.0

        px = np.mean(_x)
        if np.isnan(px):
            show_image("frame", frame)             # display image to opencv window
            show_image("track_view", track_view)   # display image to opencv window

            # show track image to webconsole
            dashboard["track_view"     ] = track_view
            dashboard["track_view_info"] = (track_view_slice.start, track_view_slice.stop, None)
            return -100.0   # special case

        steering_angle = math.atan2(track_view.shape[0] * float(3.5), (px - camera_x))

        #draw the steering direction and display on webconsole
        r = 60
        x = track_view.shape[1] // 2 + int(r * math.cos(steering_angle))
        y = track_view.shape[0]      - int(r * math.sin(steering_angle))
        cv2.line(track_view, (track_view.shape[1] // 2, track_view.shape[0]), (x, y), (255, 0, 255), 2)

        show_image("frame", frame)             # display image to opencv window
        show_image("track_view", track_view)   # display image to opencv window

        # show track image to webconsole
        dashboard["track_view"     ] = track_view
        dashboard["track_view_info"] = (track_view_slice.start, track_view_slice.stop, (np.pi/2 - steering_angle) * 180.0 / np.pi)
        return (np.pi/2 - steering_angle) * 180.0 / np.pi


    def _flatten_rgb(self, img):
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

