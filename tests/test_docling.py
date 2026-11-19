from itertools import groupby
from pathlib import Path

import numpy as np
from PIL import Image
from docling.chunking import HierarchicalChunker
from docling_core.types.doc import SectionHeaderItem, TitleItem
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import HeadingHierarchyOptions, PdfPipelineOptions, RapidOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from rapidocr.main import get_rotate_crop_image

try:
    from .vietocr_recognizer import VietOCRRecognizer
except ImportError:
    from vietocr_recognizer import VietOCRRecognizer


class RapidDetectionVietOCRModel(RapidOcrModel):
    """RapidOCR detects text lines; VietOCR recognizes each cropped line."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.recognizer = VietOCRRecognizer() if self.enabled else None

    def _read(self, image):
        pixels = np.asarray(image.convert("RGB"))

        # RapidOCR phát hiện vị trí các dòng chữ.
        detection = self.reader(
            pixels,
            use_det=True,
            use_cls=False,
            use_rec=False,
        )

        if detection is None or detection.boxes is None:
            return None

        boxes = []
        images = []

        # Cắt ảnh của từng dòng.
        for box in detection.boxes:
            crop = get_rotate_crop_image(
                pixels,
                np.asarray(box, dtype=np.float32).copy(),
            )

            if crop.size == 0:
                continue

            boxes.append(box)
            images.append(Image.fromarray(crop))

        if not images:
            return None

        # Giới hạn số ảnh mỗi lần gọi để kiểm soát VRAM.
        batch_size = 16
        lines = []

        for start in range(0, len(images), batch_size):
            batch_images = images[start:start + batch_size]
            batch_boxes = boxes[start:start + batch_size]

            texts = self.recognizer.recognize_batch(batch_images)

            for box, text in zip(batch_boxes, texts):
                if text.strip():
                    lines.append((box.tolist(), text, float("nan")))

        return lines or None


class VietOCRPdfPipeline(StandardPdfPipeline):
    def _make_ocr_model(self, art_path):
        return RapidDetectionVietOCRModel(
            enabled=self.pipeline_options.do_ocr,
            artifacts_path=art_path,
            options=self.pipeline_options.ocr_options,
            accelerator_options=self.pipeline_options.accelerator_options,
        )



def main():
    pdf_path = Path(__file__).resolve().parents[1] / "data/raw/quy_dinh_dao_tao_test_3.pdf"
    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        ocr_options=RapidOcrOptions(use_det=True, use_cls=False, use_rec=False),
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CUDA),
        heading_hierarchy_options=HeadingHierarchyOptions(enabled=True),
    )
    converter = DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_cls=VietOCRPdfPipeline, pipeline_options=pipeline_options
        )
    })
    result = converter.convert(pdf_path)

    print("\n=== Heading levels ===")
    for item, _ in result.document.iterate_items():
        if isinstance(item, TitleItem):
            print(f"TITLE: {item.text}")
        elif isinstance(item, SectionHeaderItem):
            print(f"LEVEL {item.level}: {item.text}")

    chunker = HierarchicalChunker()
    chunks = chunker.chunk(result.document)
    # Gộp các phần liên tiếp có cùng đường dẫn heading.
    for i, (headings, group) in enumerate(
        groupby(chunks, key=lambda chunk: tuple(chunk.meta.headings or [])), start=1
    ):
        content = "\n".join(chunk.text for chunk in group)
        print(f"\n{'=' * 50}\nCHUNK {i}")
        print("Headings:", list(headings))
        print("Content:", content)
        # print("Contextualized:", "\n".join([*headings, content]))


if __name__ == "__main__":
    main()
