import easyocr
import os
import re

class OcrReader:
    def __init__(self, model_dir='models'):
        # 确保模型目录存在
        os.makedirs(model_dir, exist_ok=True)
        # 检查模型文件是否存在，若不存在则自动下载
        if not os.path.exists(model_dir) or not self._model_exists(model_dir):
            print(f"[OCR] 模型目录 {model_dir} 缺失或不完整，尝试自动下载...")
            try:
                self.reader = easyocr.Reader(['en'], model_storage_directory=model_dir, download_enabled=True)
            except Exception as e:
                raise RuntimeError(f"自动下载模型失败，请手动指定路径: {e}")
        else:
            self.reader = easyocr.Reader(['en'], model_storage_directory=model_dir, download_enabled=False)

    def _model_exists(self, model_dir):
        """简单检查关键模型文件是否存在"""
        detector = os.path.join(model_dir, 'craft_mlt_25k.pth')
        recognizer = os.path.join(model_dir, 'english_g2.pth')
        return os.path.isfile(detector) and os.path.isfile(recognizer)

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