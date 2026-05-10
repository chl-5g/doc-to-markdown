import argparse
import sys
from pathlib import Path

from doc2md.converter import UnsupportedFormatError, convert, convert_batch
from doc2md.models import BatchResult


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='doc2md',
        description='Multi-format document to Markdown converter for RAG pipelines',
    )
    parser.add_argument(
        'inputs', nargs='+',
        help='Input file(s) or glob patterns',
    )
    parser.add_argument(
        '-o', '--output',
        help='Output file path (single file mode) or output directory (batch mode)',
    )
    parser.add_argument(
        '--lang', default='ch',
        help='OCR language for MinerU (default: ch)',
    )
    parser.add_argument(
        '--dpi', type=int, default=300,
        help='DPI for PDF rendering (default: 300)',
    )
    parser.add_argument(
        '--timeout', type=int, default=600,
        help='OCR timeout in seconds (default: 600)',
    )

    args = parser.parse_args()

    # Expand glob patterns
    paths = []
    for p in args.inputs:
        matched = list(Path.cwd().glob(p) if '*' in p or '?' in p else [Path(p)])
        if not matched:
            print(f'No files matched: {p}', file=sys.stderr)
            sys.exit(1)
        for mp in matched:
            if not mp.exists():
                print(f'File not found: {mp}', file=sys.stderr)
                sys.exit(1)
            paths.append(str(mp.resolve()))

    pdf_kwargs = {'lang': args.lang, 'dpi': args.dpi, 'timeout': args.timeout}

    if len(paths) == 1:
        _convert_single(paths[0], args.output, pdf_kwargs)
    else:
        _convert_batch(paths, args.output, pdf_kwargs)


def _convert_single(input_path: str, output: str | None, pdf_kwargs: dict) -> None:
    if output is None:
        output = str(Path(input_path).with_suffix('.md'))

    try:
        result = convert(input_path, **pdf_kwargs)
    except UnsupportedFormatError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    result.save(str(output))
    print(str(output))


def _convert_batch(paths: list[str], output_dir: str | None, pdf_kwargs: dict) -> None:
    if output_dir:
        outdir = Path(output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
    else:
        outdir = None

    batch = convert_batch(paths, **pdf_kwargs)

    for r in batch.results:
        if outdir:
            dest = outdir / Path(r.source_path).with_suffix('.md').name
        else:
            dest = Path(r.source_path).with_suffix('.md')
        r.save(str(dest))
        print(str(dest))

    for path, err in batch.errors:
        print(f'ERROR [{path}]: {err}', file=sys.stderr)

    if batch.error_count:
        sys.exit(1)
