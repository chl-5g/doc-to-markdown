from pathlib import Path

import pandas as pd

from doc2md.models import ConvertResult


class ExcelConverter:
    def convert(self, path: str) -> ConvertResult:
        xls = pd.ExcelFile(path)
        parts = []
        for name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=name)
            if df.empty:
                parts.append(f"## {name}\n\n*(empty sheet)*\n")
                continue
            df = df.map(lambda x: str(x).replace('\n', '<br>') if isinstance(x, str) else x)
            md = df.to_markdown(index=False)
            parts.append(f"## {name}\n\n{md}\n")
        return ConvertResult(
            content="\n".join(parts),
            source_format=Path(path).suffix.lower().lstrip("."),
            source_path=str(path),
            metadata={"sheets": xls.sheet_names},
        )
