import easyocr
import os
import re

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

    def read_number(self, image):
        try:
            result = self.reader.readtext(image, detail=0, paragraph=True)
            if not result:
                return None
            text = result[0]
            text = text.replace('O', '0').replace('I', '1').replace('l', '1').replace(',', '.')
            match = re.search(r'[\d]+\.?[\d]*', text)
            if match:
                return float(match.group())
            return None
        except Exception as e:
            print(f"[OCR] 识别异常: {e}")
            return None