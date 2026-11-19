import torch
from vietocr.tool.predictor import Predictor
from vietocr.tool.config import Cfg

class VietOCRRecognizer:
    def __init__(self):
        config = Cfg.load_config_from_name(
            "vgg_transformer"
        )

        config["device"] = (
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        config["cnn"]["pretrained"] = False
        config["predictor"]["beamsearch"] = False

        self.model = Predictor(config)

    def recognize(self, image):
        """
        image: PIL.Image chứa một dòng chữ
        return: văn bản nhận dạng
        """
        return self.model.predict(
            image.convert("RGB")
        )
    def recognize_batch(self, images):
        images = [image.convert("RGB") for image in images]
        return self.model.predict_batch(images)
