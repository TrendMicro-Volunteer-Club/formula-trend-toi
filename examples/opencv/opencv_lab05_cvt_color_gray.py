import cv2
import numpy as np

if __name__ == '__main__':
    img_bgr = cv2.imread('image_sample_01.png')
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    cv2.namedWindow('original')
    cv2.imshow('original', img_bgr)

    cv2.namedWindow('gray')
    cv2.imshow('gray', img_gray)
    cv2.waitKey()
