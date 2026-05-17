# doc2md

多格式文档转 Markdown，面向 RAG 语料处理。

## 支持的格式

| 格式 | 引擎 | 说明 |
|------|------|------|
| Excel (.xlsx/.xls) | pandas + tabulate | 多 sheet，自动生成表格，单元格换行转 `<br>` |
| Word (.docx/.doc) | mammoth + LibreOffice | 保留标题层级、列表、表格。.doc 自动转 .docx 后处理 |
| PDF（文本层） | pymupdf | 结构化提取：字号推断标题层级、坐标对齐检测表格 |
| PDF（文本层） | OpenDataLoader PDF | Java 混合引擎（规则+AI），表格/列表/代码块输出质量高，80+语言 OCR |
| PDF（扫描件）/ 图片 | MinerU pipeline | 版面分析 + OCR + 表格还原 |

> 通过 `--engine` 选择 PDF 引擎：`auto`（默认，pymupdf → MinerU OCR 回退）、`odl`、`mineru`、`pymupdf`。

> PDF 自动检测文本层（阈值 50 字符）+ 乱码率检测（有效字符 < 30% 降级 OCR）。
> 扫描件预处理：像素阈值过滤（≤50 保留为文字）+ 连通域去噪斑 + 图片合并回 PDF 再送 MinerU。
> 后处理：jieba 分词过滤低质量乱码行。

## 安装

```bash
cd /opt/doc-to-markdown
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 扫描件 OCR 支持（含 PyTorch + CUDA 依赖，约 5GB）
pip install "mineru[all]"

# OpenDataLoader PDF 支持（需 Java 11+，约 50MB）
pip install "doc2md[odl]"

# .doc 支持需要 LibreOffice
apt install libreoffice-core
```

### MinerU 持久化后端服务

MinerU 每次调用默认启动临时 API 服务，模型加载耗时 2-5 分钟。推荐部署为持久化 systemd 服务：

```bash
cat > /etc/systemd/system/mineru-api.service << 'EOF'
[Unit]
Description=MinerU FastAPI Service (Persistent)
After=network.target

[Service]
Type=simple
ExecStart=/opt/doc-to-markdown/.venv/bin/mineru-api --host 127.0.0.1 --port 8777
WorkingDirectory=/opt/doc-to-markdown
Environment=MINERU_MODEL_SOURCE=local
Environment=ALL_PROXY=
Environment=HTTP_PROXY=
Environment=HTTPS_PROXY=
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now mineru-api
```

doc2md 在 `--engine mineru` / `--engine auto`（OCR 回退）时自动连接 `http://127.0.0.1:8777`，无需冷启动等待。

## 使用

```bash
# 单文件
python -m doc2md report.xlsx                    # → report.md
python -m doc2md document.docx                  # → document.md
python -m doc2md scan.pdf -o custom.md          # → custom.md

# 批量
python -m doc2md dir/*.xlsx -o output/          # 全部转MD到output/
python -m doc2md a.xlsx b.docx c.pdf            # 多文件一起转

# OpenDataLoader PDF 引擎
python -m doc2md report.pdf --engine odl

# PDF 参数
python -m doc2md scan.pdf --lang en --dpi 200 --timeout 300
```

## Python API

```python
from doc2md import convert, convert_batch, ConvertResult, BatchResult

# 单文件
result = convert("report.xlsx")
print(result.content)        # Markdown 文本
print(result.source_format)  # "xlsx"
print(result.metadata)       # {"sheets": ["Sheet1", "Sheet2"]}
result.save("output.md")     # 写入文件

# 批量
batch = convert_batch(["a.xlsx", "b.docx", "c.pdf"])
for r in batch.results:
    r.save(f"out/{r.source_path}.md")
for path, err in batch.errors:
    print(f"FAIL {path}: {err}")
```

## 已知限制

### 扫描件 OCR
- **质量**：中文扫描件（尤其目录/多栏/底纹/水印密集的政府文件）MinerU OCR 会产生乱码后缀。预处理（像素过滤）和后处理（jieba 分词清洗）可缓解但未根治。高分辨率原文件效果更好。
- **速度**：首次运行需下载模型（~2GB），后续 GPU（A5000 24GB）8 页约 50 秒。
- **持久化服务**：推荐通过 systemd 部署 mineru-api 持久化服务（见安装章节），避免每次调用冷启动加载模型（2-5 分钟）。

### 环境/依赖
- **代理环境变量干扰**：`ALL_PROXY` / `HTTP_PROXY` 等环境变量会挟持 MinerU 的 httpx 客户端，导致本地调用走 SOCKS 代理报错（`socksio` not installed）。doc2md 已在 subprocess 中清除这些变量。
- **GPU 显存抢占**：如果其他进程（如 Ollama）占用大量显存，MinerU VLM 模型加载失败时静默回退 CPU pipeline，速度大幅下降。运行前建议 `ollama stop` 释放显存。
- **LibreOffice**：`.doc` 格式需要系统安装 `libreoffice-core`，未安装时抛 RuntimeError 提示。

### 解析边界
- **PDF 伪文本层**：部分 PDF 有文本层但内嵌字体丢失 Unicode 映射，提取出 CID 乱码或方块字。已加入乱码率检测（有效字符 < 30% 自动降级 OCR）。
- **Excel 长单元格**：含换行符的单元格会将 `\n` 替换为 `<br>` 以防止 Markdown 表格结构崩溃。
- **超大 PDF 预处理**：高 DPI 扫描件预处理（Otsu + 连通域分析）极耗 CPU（300DPI、34MB、8 页约 12 分钟），建议质量好的扫描件跳过预处理直接送 MinerU。

## TODO

- [ ] PDF 预处理性能优化：大页数高 DPI 时 Otsu 逐页计算瓶颈，考虑自适应降 DPI 或按页复杂度分流
- [ ] MinerU GPU 利用率保障：检测可用显存，不足时显式报错而非静默退 CPU
- [x] FastAPI 服务化：mineru-api systemd 持久化服务已部署，模型常驻 GPU 显存，消除冷启动
- [ ] VLM Fallback 引擎：复杂页面直送 Qwen-VL / Claude 输出 Markdown（需 API key）
- [ ] 图片提取：Word/PDF 内嵌图片保存到 `./images/` 并在 Markdown 中保留链接
- [ ] 后处理 LLM 纠错：轻量模型（Qwen-2.5-7B）修正 OCR 错别字和断行
- [ ] Excel 多级表头检测：合并单元格跨行/列的 Markdown 还原
- [ ] Docker GPU 镜像构建稳定化
- [ ] `.doc` 的 LibreOffice 转换增加超时和临时文件清理

## 依赖

```
mammoth                   — Word .docx 解析
pandas + tabulate         — Excel 读取和表格生成
openpyxl                  — .xlsx 后端
pymupdf                   — PDF 文本层提取 + 图片渲染
opencv-python-headless    — 扫描件预处理（阈值过滤/去噪）
jieba                     — OCR 后处理分词清洗
opendataloader-pdf        — OpenDataLoader PDF 引擎（可选，约 50MB）
mineru[all]               — PDF/图片 OCR + 版面分析（可选，约 5GB）
mineru-api                 — 持久化 FastAPI 后端服务，模型常驻 GPU 显存
```

## License

MIT
