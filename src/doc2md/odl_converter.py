import logging
import shutil
import tempfile
from pathlib import Path

from doc2md.models import ConvertResult

logger = logging.getLogger(__name__)


class OdlConverter:
    def convert(self, path: str) -> ConvertResult:
        source_path = Path(path).resolve()

        try:
            import opendataloader_pdf
        except ImportError:
            raise RuntimeError(
                "opendataloader-pdf not found. Install: pip install 'doc2md[odl]'"
            )

        if not shutil.which('java'):
            raise RuntimeError(
                "Java not found. opendataloader-pdf requires Java 11+."
            )

        tmpdir = Path(tempfile.mkdtemp())
        try:
            opendataloader_pdf.convert(
                input_path=[str(source_path)],
                output_dir=str(tmpdir),
                format='markdown',
            )
            md_files = list(tmpdir.glob('*.md'))
            if not md_files:
                raise RuntimeError(
                    f'OpenDataLoader produced no .md output for {source_path.name}'
                )
            content = md_files[0].read_text(encoding='utf-8')
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        return ConvertResult(
            content=content,
            source_format='pdf',
            source_path=str(path),
            metadata={'engine': 'opendataloader-pdf'},
        )
