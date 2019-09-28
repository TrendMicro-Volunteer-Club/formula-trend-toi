import cv2
import numpy as np

if __name__ == '__main__':
    img = cv2.imread('image_sample_03.png')
    cv2.namedWindow('original')
    cv2.imshow('original', img)

    img_bottom = img[120:, :, :]
    grayed = cv2.cvtColor(img_bottom, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grayed, (3, 3), 0)

    masked_edges = cv2.Canny(blurred, 10, 150)
    cv2.namedWindow('canny')
    cv2.imshow('canny', masked_edges)

    masked_edges_blurred = cv2.GaussianBlur(masked_edges, (3, 3), 0)
    cv2.namedWindow('canny_blurred')
    cv2.imshow('canny_blurred', masked_edges_blurred)
    
    lines = cv2.HoughLinesP(masked_edges_blurred, 1, np.pi/180, 50, 30, 80)
    if lines is not None:
        for line in lines:
            for x1, y1, x2, y2 in line:
                print('({}, {}) -> ({}, {})'.format(x1, y1, x2, y2))
                cv2.line(img_bottom, (x1, y1), (x2, y2), (0, 255, 0), 2)

    cv2.namedWindow('detected_results')
    cv2.imshow('detected_results', img_bottom)
    cv2.waitKey()