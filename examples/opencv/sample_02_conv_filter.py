import cv2
import numpy as np

if __name__ == '__main__':
    # 讀入影像
    img = cv2.imread('image_sample_04.png')

    # 轉灰階
    img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # 建立濾波器
    kernel_mask = np.array([[-1, 0, +1],
                            [-1, 0, +1],
                            [-1, 0, +1]])

    # 將img_gray透過kernel_mask進行濾波
    img_processed = cv2.filter2D(img_gray, -1, kernel_mask)

    # 顯示結果
    cv2.namedWindow('sample')
    cv2.imshow('sample', img)

    cv2.namedWindow('result')
    cv2.imshow('result', img_processed)
    cv2.waitKey()
