import easyocr
import os
import re

class OcrReader:
    def __init__(self, model_dir='models'):
        if not os.path.exists(model_dir) or not os.listdir(model_dir):
            print(f"[OCR] 模型目录 {model_dir} 不存在或为空，尝试自动下载...")
            try:
                self.reader = easyocr.Reader(['en'], model_storage_directory=model_dir, download_enabled=True)
            except Exception as e:
                raise RuntimeError(f"自动下载失败，请手动指定模型路径: {e}")
        else:
            self.reader = easyocr.Reader(['en'], model_storage_directory=model_dir, download_enabled=False)

    def read_number(self, image):
        """识别图像中的数字，返回 float 或 None"""
        try:
            result = self.reader.readtext(image, detail=0, paragraph=True)
            if not result:
                return None
            text = result[0]
            # 替换常见混淆字符
            text = text.replace('O', '0').replace('I', '1').replace('l', '1').replace(',', '.')
            match = re.search(r'[\d]+\.?[\d]*', text)
            if match:
                return float(match.group())
            return None
        except Exception as e:
            print(f"[OCR] 识别异常: {e}")
            return None