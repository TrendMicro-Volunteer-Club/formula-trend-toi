import cv2
import numpy as np
#
class HoG:
    def calculate_hog(self, angle, mag, bins, is_count_by_mag):
        hog_deg_bins = np.array(range(0,180,180//bins))
        hog_histogram = np.zeros(hog_deg_bins.shape)
        angle_index = np.digitize(angle, hog_deg_bins)
        for y,mag_y in enumerate(mag):
            for x,mag_x in enumerate(mag_y):
                _hist_idx = angle_index[y,x]
                if is_count_by_mag: _cntee = mag_x
                else: _cntee = 1
                hog_histogram[_hist_idx] += _cntee
        return hog_histogram, hog_deg_bins
    #
    def create(self, img_list=None):
        if img_list is not None: self.images = img_list
        #
        hog_mat = []
        for img in self.images:
            assert type(img) is np.ndarray, \
                "HoG feature extractor are accept ndarray image only, got {} instead".format(type(img))
            sign_img_scaled = cv2.resize(img, self.HOG_IMAGE_SIZE)
            try:
                sign_img_gray = cv2.cvtColor(sign_img_scaled, cv2.COLOR_RGB2GRAY)
            except: pass # If unable to parse from RGB 
            gx = cv2.Sobel(sign_img_gray, cv2.CV_8U, 0, 1, 1)
            gy = cv2.Sobel(sign_img_gray, cv2.CV_8U, 1, 0, 1)
            mag, angle = cv2.cartToPolar(gx.astype(np.float32),gy.astype(np.float32), angleInDegrees=True)
            img_h, img_w = mag.shape
            nCellW, nCellH = img_w//self.HOG_CELL_SIZE, img_h//self.HOG_CELL_SIZE
            Cell_Mags, Cell_Angles, Cell_HoG = [], [], None

            for hcell in range(nCellH):
                _row_mag, _row_angle = [],[]
                for wcell in range(nCellW):
                    w_start, w_end = (wcell)*self.HOG_CELL_SIZE, None if wcell==nCellW-1 else (wcell+1)*self.HOG_CELL_SIZE
                    h_start, h_end = (hcell)*self.HOG_CELL_SIZE, None if hcell==nCellH-1 else (hcell+1)*self.HOG_CELL_SIZE
                    _row_mag.append(mag[h_start:h_end,w_start:w_end])
                    _row_angle.append(angle[h_start:h_end,w_start:w_end])
                Cell_Mags.append(_row_mag)
                Cell_Angles.append(_row_angle)
            # Calculating Oriented Histogram for each Cell
            Cell_HoG = None
            for y in range(nCellH):
                for x in range(nCellW):
                    _angle = Cell_Angles[y][x]
                    _mag   = Cell_Mags[y][x]
                    hog, bins = self.calculate_hog(_angle, _mag, self.HOG_DEGREE_BINS, self.FLAG_COUNT_BY_MAGNITUDE)
                    if Cell_HoG is None:
                        Cell_HoG = np.zeros((nCellH, nCellW, len(bins)))
                    Cell_HoG[y,x] = hog
            # Creating HoG blocks
            block_w, block_h = self.HOG_BLOCK_SIZE
            hog_vector_list = []
            for iy in range(0,nCellH-block_w+1, self.HOG_BLOCK_STRIDE[0]):
                for ix in range(0,nCellW-block_h+1, self.HOG_BLOCK_STRIDE[1]):
                    _ = Cell_HoG[iy:iy+block_h, ix:ix+block_w]
                    hog_vector_list.append(_.flatten('A'))
            hog_vector = np.concatenate(hog_vector_list)
            hog_mat.append(hog_vector)
        if len(hog_mat)>0:
          return np.vstack(hog_mat)
        return np.array([])
        
    #
    def __init__(self, img_list=[]):
        self.images = img_list
        self.HOG_DEGREE_BINS = 16
        self.HOG_IMAGE_SIZE  = (40,20)
        self.HOG_CELL_SIZE   = 10
        self.HOG_BLOCK_SIZE  = (2, 2)   #  2x2 Cells (width, height)
        self.HOG_BLOCK_STRIDE = (1, 1) 
        self.FLAG_COUNT_BY_MAGNITUDE = False
