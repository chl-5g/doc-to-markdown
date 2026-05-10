import shutil
import subprocess
import tempfile
from pathlib import Path

import mammoth

from doc2md.models import ConvertResult


class WordConverter:
    def convert(self, path: str) -> ConvertResult:
        source = Path(path)
        ext = source.suffix.lower()

        if ext == '.doc':
            source = self._doc_to_docx(source)

        with open(source, 'rb') as f:
            result = mammoth.convert_to_markdown(f)

        return ConvertResult(
            content=result.value,
            source_format='docx',
            source_path=str(path),
            metadata={'warnings': [str(m) for m in result.messages]},
        )

    def _doc_to_docx(self, path: Path) -> Path:
        if not shutil.which('libreoffice'):
            raise RuntimeError(
                '.doc requires LibreOffice. Install: apt install libreoffice-core'
            )
        tmpdir = Path(tempfile.mkdtemp())
        cmd = [
            'libreoffice',
            '--headless',
            '--convert-to', 'docx',
            '--outdir', str(tmpdir),
            str(path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        converted = list(tmpdir.glob('*.docx'))
        if not converted:
            raise RuntimeError(f'LibreOffice failed to convert {path}')
        return converted[0]
