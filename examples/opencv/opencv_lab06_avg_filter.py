import cv2
import numpy as np

if __name__ == '__main__':
    img = cv2.imread('image_sample_04.png')

    kernel_mask = np.ones(shape=(5, 5))
    """
    # 和下列動作相等
    kernel_mask = np.array([[1, 1, 1, 1, 1],
                            [1, 1, 1, 1, 1],
                            [1, 1, 1, 1, 1],
                            [1, 1, 1, 1, 1],
                            [1, 1, 1, 1, 1]])
    kernel_mask = kernel_mask/np.sum(kernel_mask)
    """

    img_processed = cv2.filter2D(img, -1, kernel_mask)

    cv2.namedWindow('sample')
    cv2.imshow('sample', img)

    cv2.namedWindow('result')
    cv2.imshow('result', img_processed)
    cv2.waitKey()