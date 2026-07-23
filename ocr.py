import easyocr
import os
import re
import cv2
import numpy as np

class OcrReader:
    def __init__(self, model_dir='models'):
        os.makedirs(model_dir, exist_ok=True)
        det_path = os.path.join(model_dir, 'craft_mlt_25k.pth')
        rec_path = os.path.join(model_dir, 'english_g2.pth')
        download = not (os.path.exists(det_path) and os.path.exists(rec_path))

        try:
            self.reader = easyocr.Reader(['en'], model_storage_directory=model_dir, download_enabled=download)
        except Exception as e:
            raise RuntimeError(f"OCR初始化失败: {e}")

    def preprocess(self, pil_image, scale=2.0, contrast=1.5, invert=False, 
                   blur_k=0, sharpen=False, binarize=False, thresh_val=0, morph_val=0):
        """
        图像预处理流水线：
        放大 -> 调对比度 -> 灰度化 -> 颜色反色 -> 降噪/锐化 -> 二值化 -> 笔画加粗/瘦身
        """
        img_np = np.array(pil_image)
        if len(img_np.shape) == 2:
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
        else:
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

        # 1. 放大倍数 (解决分辨率低问题)
        if scale > 1.0:
            h, w = img_bgr.shape[:2]
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            img_bgr = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        # 2. 对比度调节
        if contrast != 1.0:
            img_bgr = cv2.convertScaleAbs(img_bgr, alpha=contrast, beta=0)

        # 转灰度
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        # 3. 颜色反色 (专治黑底白字、LED红字数码管)
        if invert:
            img_gray = cv2.bitwise_not(img_gray)

        # 4. 高斯模糊降噪 (去除背景网格噪点)
        if blur_k > 0:
            k = blur_k if blur_k % 2 != 0 else blur_k + 1
            img_gray = cv2.GaussianBlur(img_gray, (k, k), 0)

        # 5. 边缘锐化 (专治字体边缘模糊发虚)
        if sharpen:
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            img_gray = cv2.filter2D(img_gray, -1, kernel)

        # 6. 二值化
        if binarize:
            if thresh_val <= 0:
                _, img_gray = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            else:
                _, img_gray = cv2.threshold(img_gray, int(thresh_val), 255, cv2.THRESH_BINARY)

        # 7. 笔画加粗/瘦身 (修复断笔或文字粘连)
        if morph_val != 0:
            kernel = np.ones((3, 3), np.uint8)
            if morph_val > 0:
                # 膨胀：加粗笔画
                img_gray = cv2.dilate(img_gray, kernel, iterations=abs(morph_val))
            else:
                # 腐蚀：细化笔画
                img_gray = cv2.erode(img_gray, kernel, iterations=abs(morph_val))

        return img_gray

    def read_number(self, pil_image, scale=2.0, contrast=1.5, invert=False, 
                    blur_k=0, sharpen=False, binarize=False, thresh_val=0, morph_val=0):
        """
        返回 tuple: (提取到的浮点数或None, 原始识别文本信息, 预处理后的图像)
        """
        try:
            processed_img = self.preprocess(
                pil_image, scale, contrast, invert, 
                blur_k, sharpen, binarize, thresh_val, morph_val
            )

            # 读取字符
            results = self.reader.readtext(
                processed_img,
                allowlist='0123456789.OoIil',
                detail=0,
                paragraph=False
            )

            raw_text = " ".join(results).strip()
            if not raw_text:
                return None, "未识别到字符", processed_img

            # 替换常见混淆字符
            clean_text = raw_text.replace('O', '0').replace('o', '0').replace('I', '1').replace('l', '1').replace(' ', '')
            match = re.search(r'\d+\.?\d*', clean_text)
            if match:
                return float(match.group()), raw_text, processed_img
            return None, f"未检测到有效数字({raw_text})", processed_img

        except Exception as e:
            return None, f"错误: {str(e)}", None