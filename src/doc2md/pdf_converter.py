import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from doc2md.models import ConvertResult

try:
    import jieba
    _has_jieba = True
except ImportError:
    jieba = None
    _has_jieba = False

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif', '.webp'}
MIN_TEXT_LENGTH = 50


# ---- Chinese OCR post-processing ----


def _clean_text(text: str) -> str:
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append('')
            continue
        if _has_jieba:
            words = list(jieba.cut(stripped))
            valid = sum(1 for w in words if len(w) > 1)
            total = max(len(words), 1)
            if valid / total < 0.5:
                continue
        else:
            cn_chars = sum(1 for c in stripped if '一' <= c <= '鿿')
            total = max(len(stripped.replace(' ', '')), 1)
            if cn_chars / total < 0.3:
                continue
        cleaned.append(stripped)
    return '\n'.join(cleaned)


# ---- Pixel-level preprocessing for black-and-white scanned documents ----


def _preprocess_pdf_pages(pdf_path: Path, work_dir: Path, dpi: int = 300,
                          text_threshold: int = 50) -> list[Path]:
    import fitz

    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.warning('opencv-python not available, falling back to raw rendering')
        return _render_pdf_pages_raw(pdf_path, work_dir, dpi)

    doc = fitz.open(str(pdf_path))
    image_paths = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img

        otsu_thresh, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        effective_thresh = max(min(otsu_thresh, 120), text_threshold)
        mask = (gray <= effective_thresh)
        cleaned = np.where(mask, gray, 255).astype(np.uint8)

        binary_inv = (cleaned < 255).astype(np.uint8) * 255
        filtered = _remove_small_components(binary_inv, min_area=10)
        cleaned = cv2.bitwise_not(filtered)

        out_path = work_dir / f'page_{i:04d}.png'
        cv2.imwrite(str(out_path), cleaned)
        image_paths.append(out_path)

    doc.close()
    logger.info('Preprocessed %d pages (Otsu, clip=[%d,120], speck removal)',
                len(image_paths), text_threshold)
    return image_paths


def _remove_small_components(binary: 'np.ndarray', min_area: int = 10) -> 'np.ndarray':
    import cv2
    import numpy as np

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    mask = np.zeros_like(binary, dtype=np.uint8)
    for label_id in range(1, num_labels):
        if stats[label_id, cv2.CC_STAT_AREA] >= min_area:
            mask[labels == label_id] = 255
    return mask


def _render_pdf_pages_raw(pdf_path: Path, work_dir: Path, dpi: int = 300) -> list[Path]:
    import fitz

    doc = fitz.open(str(pdf_path))
    image_paths = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        out_path = work_dir / f'page_{i:04d}.png'
        pix.save(str(out_path))
        image_paths.append(out_path)
    doc.close()
    return image_paths


def _images_to_pdf(image_paths: list[Path], output_path: Path) -> Path:
    import fitz

    doc = fitz.open()
    for ip in image_paths:
        img = fitz.open(str(ip))
        rect = img[0].rect
        page = doc.new_page(width=rect.width, height=rect.height)
        page.insert_image(rect, filename=str(ip))
        img.close()
    doc.save(str(output_path))
    doc.close()
    return output_path


# ---- PdfConverter ----


class PdfConverter:
    def __init__(self, timeout: int = 600, lang: str = 'ch', dpi: int = 300):
        self.timeout = timeout
        self.lang = lang
        self.dpi = dpi

    def convert(self, path: str) -> ConvertResult:
        source_path = Path(path).resolve()
        ext = source_path.suffix.lower()

        if ext == '.pdf':
            text_content = self._extract_text_pymupdf(source_path)
            if text_content and len(text_content.strip()) >= MIN_TEXT_LENGTH and not self._is_text_garbled(text_content):
                return ConvertResult(
                    content=text_content,
                    source_format='pdf',
                    source_path=str(path),
                    metadata={'engine': 'pymupdf', 'method': 'text-extraction-structured'},
                )
            logger.info('PDF has insufficient text layer, running OCR')

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir).resolve()

            if ext == '.pdf':
                page_images = _preprocess_pdf_pages(source_path, tmpdir_path, dpi=self.dpi)
                merged_pdf = _images_to_pdf(page_images, tmpdir_path / 'merged.pdf')
                ocr_input = merged_pdf
            elif ext in IMAGE_EXTENSIONS:
                ocr_input = source_path
            else:
                ocr_input = source_path

            content = self._run_ocr(ocr_input, tmpdir_path)
            content = _clean_text(content)

        return ConvertResult(
            content=content,
            source_format=ext.lstrip('.'),
            source_path=str(path),
            metadata={
                'engine': 'mineru',
                'post_processed': True,
            },
        )

    def _run_ocr(self, input_path: Path, output_dir: Path) -> str:
        if not shutil.which('mineru'):
            raise RuntimeError("MinerU not found. Install: pip install 'mineru[all]'")
        job_dir = output_dir / 'output'
        job_dir.mkdir(exist_ok=True)
        cmd = [
            'mineru',
            '-p', str(input_path),
            '-o', str(job_dir),
            '-b', 'hybrid-auto-engine',
            '-l', self.lang,
            '--api-url', 'http://127.0.0.1:8777',
        ]
        self._exec(cmd, str(input_path))

        md_files = list(job_dir.glob(f'**/{input_path.stem}*.md'))
        if not md_files:
            md_files = list(job_dir.glob('**/*.md'))
        if not md_files:
            raise RuntimeError(f'MinerU produced no .md output for {input_path}')

        return md_files[0].read_text(encoding='utf-8')

    def _exec(self, cmd: list[str], label: str) -> None:
        env = os.environ.copy()
        for k in ('ALL_PROXY', 'all_proxy', 'HTTP_PROXY', 'http_proxy',
                  'HTTPS_PROXY', 'https_proxy', 'NO_PROXY', 'no_proxy'):
            env.pop(k, None)
        env.setdefault('MINERU_FORCE_VLM_OCR_ENABLE', '1')
        logger.info('Running: %s', ' '.join(cmd))
        try:
            subprocess.run(cmd, check=True, timeout=self.timeout,
                           capture_output=True, env=env)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f'MinerU timed out after {self.timeout}s on {label}')
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f'MinerU failed on {label}: {stderr}')

    # ---- Structured text extraction ----

    @staticmethod
    def _is_text_garbled(text: str) -> bool:
        if not text or not text.strip():
            return True
        cn = sum(1 for c in text if '一' <= c <= '鿿')
        en = sum(1 for c in text if c.isalpha())
        digits = sum(1 for c in text if c.isdigit())
        spaces = sum(1 for c in text if c.isspace())
        total = max(len(text), 1)
        meaningful = cn + en + digits + spaces
        return meaningful / total < 0.3

    def _extract_text_pymupdf(self, path: Path) -> str:
        try:
            import fitz
        except ImportError:
            return ''

        doc = fitz.open(str(path))
        parts = []

        for page in doc:
            blocks = page.get_text('dict').get('blocks', [])
            if not blocks:
                continue

            body_size = self._median_body_size(blocks)
            page_parts = []
            for b in sorted(blocks, key=lambda b: (b['bbox'][1], b['bbox'][0])):
                if b['type'] == 1:  # image block, skip
                    continue
                text = self._block_text(b)
                if not text:
                    continue

                max_size = max(
                    (s['size'] for line in b['lines'] for s in line['spans']),
                    default=0,
                )

                if body_size and max_size >= body_size * 1.3:
                    level = 1 if max_size >= body_size * 1.6 else 2 if max_size >= body_size * 1.4 else 3
                    page_parts.append(f"{'#' * level} {text}")
                elif self._is_table_block(b):
                    page_parts.append(self._block_to_table(b))
                else:
                    page_parts.append(text)

            if page_parts:
                parts.append('\n\n'.join(page_parts))

        doc.close()
        return '\n\n'.join(parts)

    @staticmethod
    def _median_body_size(blocks) -> float | None:
        sizes = []
        for b in blocks:
            if b['type'] == 0:
                for line in b['lines']:
                    for span in line['spans']:
                        sizes.append(span['size'])
        if not sizes:
            return None
        return sorted(sizes)[len(sizes) // 2]

    @staticmethod
    def _block_text(block) -> str:
        texts = []
        for line in block['lines']:
            line_text = ' '.join(s['text'] for s in line['spans']).strip()
            if line_text:
                texts.append(line_text)
        return ' '.join(texts)

    @staticmethod
    def _is_table_block(block) -> bool:
        if len(block['lines']) < 2:
            return False
        span_counts = [len(line['spans']) for line in block['lines']]
        if len(set(span_counts)) != 1 or span_counts[0] < 2:
            return False
        first_x = [s['bbox'][0] for s in block['lines'][0]['spans']]
        for line in block['lines'][1:]:
            line_x = [s['bbox'][0] for s in line['spans']]
            if any(abs(a - b) > 5 for a, b in zip(first_x, line_x)):
                return False
        return True

    @staticmethod
    def _block_to_table(block) -> str:
        rows = []
        for line in block['lines']:
            cells = [s['text'].strip() for s in line['spans']]
            rows.append(cells)
        if not rows:
            return ''

        col_count = max(len(r) for r in rows)
        md_rows = ['| ' + ' | '.join(rows[0]) + ' |']
        md_rows.append('| ' + ' | '.join(['---'] * col_count) + ' |')
        for row in rows[1:]:
            padded = row + [''] * (col_count - len(row))
            md_rows.append('| ' + ' | '.join(padded) + ' |')

        return '\n'.join(md_rows)
