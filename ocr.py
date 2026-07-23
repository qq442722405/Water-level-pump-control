import easyocr
import os
import re
import cv2
import numpy as np

class OcrReader:
    def __init__(self, model_dir='models'):
        os.makedirs(model_dir, exist_ok=True)
        if not self._model_exists(model_dir):
            print(f"[OCR] 模型目录 {model_dir} 缺失，自动下载...")
            try:
                self.reader = easyocr.Reader(['en'], model_storage_directory=model_dir, download_enabled=True)
            except Exception as e:
                raise RuntimeError(f"自动下载模型失败: {e}")
        else:
            self.reader = easyocr.Reader(['en'], model_storage_directory=model_dir, download_enabled=False)

    def _model_exists(self, model_dir):
        detector = os.path.join(model_dir, 'craft_mlt_25k.pth')
        recognizer = os.path.join(model_dir, 'english_g2.pth')
        return os.path.isfile(detector) and os.path.isfile(recognizer)

    def preprocess(self, pil_image, scale=2.0, contrast=1.5, grayscale=True, invert=False, binarize=False, thresh_val=0):
        """图像预处理核心逻辑：放大 -> 调对比度 -> 灰度 -> 反色 -> 二值化"""
        img_np = np.array(pil_image)
        if len(img_np.shape) == 2:
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
        else:
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

        # 1. 图像放大 (极大幅度提升微小文字识别率)
        if scale > 1.0:
            h, w = img_bgr.shape[:2]
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            img_bgr = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        # 2. 对比度调节
        if contrast != 1.0:
            img_bgr = cv2.convertScaleAbs(img_bgr, alpha=contrast, beta=0)

        # 3. 灰度化
        if grayscale or binarize:
            img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        else:
            img_gray = img_bgr

        # 4. 反色 (适用于暗色背景、LED数码管)
        if invert:
            img_gray = cv2.bitwise_not(img_gray)

        # 5. 二值化 (黑白分明)
        if binarize:
            if len(img_gray.shape) == 3:
                img_gray = cv2.cvtColor(img_gray, cv2.COLOR_BGR2GRAY)
            if thresh_val <= 0:
                # 0 表示开启 Otsu 自动阈值
                _, img_gray = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            else:
                _, img_gray = cv2.threshold(img_gray, int(thresh_val), 255, cv2.THRESH_BINARY)

        return img_gray

    def read_number(self, pil_image, scale=2.0, contrast=1.5, grayscale=True, invert=False, binarize=False, thresh_val=0):
        try:
            # 执行预处理
            processed_img = self.preprocess(pil_image, scale, contrast, grayscale, invert, binarize, thresh_val)

            # EasyOCR 限制仅允许数字与小数点
            result = self.reader.readtext(
                processed_img,
                allowlist='0123456789.',
                detail=0,
                paragraph=True,
                mag_ratio=1.0
            )

            if not result:
                return None, processed_img

            text = "".join(result).replace(' ', '').replace('O', '0').replace('o', '0')
            match = re.search(r'\d+\.?\d*', text)
            if match:
                return float(match.group()), processed_img
            return None, processed_img
        except Exception as e:
            print(f"[OCR] 识别处理异常: {e}")
            return None, None
