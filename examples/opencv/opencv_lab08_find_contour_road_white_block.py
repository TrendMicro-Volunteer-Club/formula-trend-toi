import cv2
import numpy as np

if __name__ == '__main__':
    img = cv2.imread('image_sample_04.png')
    cv2.namedWindow('original')
    cv2.imshow('original', img)

    img_bottom = img[120:, :, :]
    blurred = cv2.GaussianBlur(img_bottom, (3, 3), 0)
    cv2.namedWindow('blurred')
    cv2.imshow('blurred', blurred)

    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    white_mask = cv2.inRange(hsv, (0,0,245), (180,30,255))
    white_masks = np.repeat(white_mask[:, :, np.newaxis], 3, axis=2)
    img_masked = img_bottom.copy()
    img_masked[white_masks == 0] = 0

    contours, hierarchy = cv2.findContours(white_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        print('x={}, y={}, width={}, height={}'.format(x, y, w, h))
        cv2.rectangle(img_masked, (x,y), (x+w, y+h), (0,255,0), 2)

    cv2.namedWindow('masked')
    cv2.imshow('masked', img_masked)
    cv2.waitKey()