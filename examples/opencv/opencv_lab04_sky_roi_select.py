import cv2
import numpy as np

if __name__ == '__main__':
    img_bgr = cv2.imread('image_sample_01.png')
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    
    sky_mask = cv2.inRange(img_hsv, (100,40,120), (120,255,255))

    mask = np.repeat(sky_mask[:, :, np.newaxis], 3, axis=2)

    img_masked = img_bgr.copy()
    img_masked[mask == 0] = 0

    cv2.namedWindow('original')
    cv2.imshow('original', img_bgr)

    cv2.namedWindow('img_masked')
    cv2.imshow('img_masked', img_masked)
    cv2.waitKey()
