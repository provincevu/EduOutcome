from itertools import groupby
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from docling.chunking import HierarchicalChunker
from docling_core.types.doc import BoundingBox, CoordOrigin, SectionHeaderItem, TitleItem
from docling_core.types.doc.page import TextCell
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import HeadingHierarchyOptions, OcrMode, PdfPipelineOptions, RapidOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel
from docling.utils.orientation import ocr_box_to_bounding_rectangle
from docling.utils.profiling import TimeRecorder
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from rapidocr.main import get_rotate_crop_image

try:
    from .vietocr_recognizer import VietOCRRecognizer
except ImportError:
    from vietocr_recognizer import VietOCRRecognizer


class RapidDetectionVietOCRModel(RapidOcrModel):
    """Use RapidOCR for detection and VietOCR for recognition."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.recognizer = VietOCRRecognizer() if self.enabled else None

    def _save_detection_preview(self, image, polygons, page_no, region_no):
        output_dir = Path(__file__).resolve().parents[1] / "data/processed/rapid_detection_debug"
        output_dir.mkdir(parents=True, exist_ok=True)
        preview = image.convert("RGB").copy()
        draw = ImageDraw.Draw(preview)
        width = max(2, round(max(preview.size) / 1200))
        for index, polygon in enumerate(polygons, start=1):
            points = [(float(x), float(y)) for x, y in polygon]
            if len(points) < 2:
                continue
            draw.line(points + [points[0]], fill="red", width=width)
            draw.text(points[0], str(index), fill="blue", stroke_width=1, stroke_fill="white")
        output_path = output_dir / f"page_{page_no:04d}_region_{region_no:02d}.png"
        preview.save(output_path)
        print(f"RapidOCR detection: {len(polygons)} boxes -> {output_path}")

    def _read(self, image, page_no, region_no):
        pixels = np.asarray(image.convert("RGB"))
        detection = self.reader(pixels, use_det=True, use_cls=False, use_rec=False)
        polygons = [] if detection is None or detection.boxes is None else detection.boxes
        self._save_detection_preview(image, polygons, page_no, region_no)
        boxes, images = [], []
        for polygon in polygons:
            points = np.asarray(polygon, dtype=np.float32)
            crop = get_rotate_crop_image(pixels, points.copy())
            if crop.size == 0:
                continue
            left, top = points.min(axis=0)
            right, bottom = points.max(axis=0)
            boxes.append((float(left), float(top), float(right), float(bottom)))
            images.append(Image.fromarray(crop))

        lines = []
        for start in range(0, len(images), 16):
            texts = self.recognizer.recognize_batch(images[start:start + 16])
            for box, text in zip(boxes[start:start + 16], texts):
                if text.strip():
                    lines.append((box, text))
        return lines

    def __call__(self, conv_res, page_batch):
        if not self.enabled:
            yield from page_batch
            return

        for page in page_batch:
            assert page._backend is not None
            if not page._backend.is_valid():
                yield page
                continue
            with TimeRecorder(conv_res, "ocr"):
                cells = []
                for region_no, rect in enumerate(self.get_ocr_rects(page), start=1):
                    if rect.area() == 0:
                        continue
                    image = page._backend.get_page_image(scale=self.scale, cropbox=rect)
                    for box, text in self._read(image, page.page_no, region_no):
                        left, top, right, bottom = box
                        cells.append(TextCell(
                            index=len(cells), text=text, orig=text,
                            # VietOCR's predict_batch does not return confidence.
                            confidence=float("nan"), from_ocr=True,
                            rect=ocr_box_to_bounding_rectangle(
                                BoundingBox.from_tuple(
                                    coord=(left, top, right, bottom),
                                    origin=CoordOrigin.TOPLEFT,
                                ),
                                original_offset=rect, scale=self.scale,
                                orientation=0, im_size=image.size,
                            ),
                        ))
                self.post_process_cells(cells, page, conv_res)
            yield page


class VietOCRPdfPipeline(StandardPdfPipeline):
    def _make_ocr_model(self, art_path):
        return RapidDetectionVietOCRModel(
            enabled=self.pipeline_options.do_ocr,
            artifacts_path=art_path,
            options=self.pipeline_options.ocr_options,
            accelerator_options=self.pipeline_options.accelerator_options,
        )



def main():
    pdf_path = Path(__file__).resolve().parents[1] / "data/raw/quy_dinh_dao_tao_test_1.pdf"
    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        ocr_options=RapidOcrOptions(mode=OcrMode.FULL_PAGE, use_det=True, use_cls=False, use_rec=False),
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CUDA),
        heading_hierarchy_options=HeadingHierarchyOptions(enabled=True),
    )
    converter = DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_cls=VietOCRPdfPipeline, pipeline_options=pipeline_options
        )
    })
    result = converter.convert(pdf_path)

    output_path = Path(__file__).resolve().parents[1] / "data/processed" / f"{pdf_path.stem}_chunks_rapid.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as output:
        def emit(*args):
            print(*args)
            print(*args, file=output)

        emit("\n=== Heading levels ===")
        for item, _ in result.document.iterate_items():
            if isinstance(item, TitleItem):
                emit(f"TITLE: {item.text}")
            elif isinstance(item, SectionHeaderItem):
                emit(f"LEVEL {item.level}: {item.text}")

        chunker = HierarchicalChunker()
        chunks = chunker.chunk(result.document)
        for i, (headings, group) in enumerate(
            groupby(chunks, key=lambda chunk: tuple(chunk.meta.headings or [])), start=1
        ):
            content = "\n".join(chunk.text for chunk in group)
            emit(f"\n{'=' * 50}\nCHUNK {i}")
            emit("Headings:", list(headings))
            emit("Content:", content)

    print(f"\nĐã lưu kết quả vào: {output_path}")


if __name__ == "__main__":
    main()
