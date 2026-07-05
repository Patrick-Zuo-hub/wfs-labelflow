# WFS 标签与货代物流标签自动拆分、插入、合并工具需求文档

## 1. 项目目标

本工具用于批量处理多组标签文件。每一组标签由以下文件组成：

1. WFS 标签 PDF，简称 `W`
2. WFS 标签对应的 ZPL/TXT 文档
3. 货代物流标签 PDF，简称 `L`

系统需要通过 WFS 标签的 ZPL/TXT 文档精准识别每一页 WFS 标签对应的 SKU、箱标信息以及是否为托盘标签。随后按照 SKU 维度拆分 WFS 标签，并按顺序将货代物流标签分配给对应的 WFS 箱标，最终生成按 SKU 汇总后的 PDF 文件。

核心目标：

- 支持一次处理最多 5 组标签。
- 每组标签内部独立解析、校验、处理。
- 同 SKU 跨组最终合并为一个 PDF。
- 合并时只能简单追加，不能打乱任何单组内部的标签顺序。
- 输出完成后清理数据库记录和临时文件，避免残余数据影响下次生产。

---

## 2. 术语定义

### 2.1 一组标签

一组标签指一次完整匹配处理所需的三个文件：

```text
WFS 标签 PDF
WFS 标签 ZPL/TXT 文档
货代物流标签 PDF
```

示例：

```text
第 1 组：
WFS 标签：WFS_001.pdf
WFS ZPL/TXT：WFS_001.txt
货代标签：L_001.pdf
```

### 2.2 WFS 标签 PDF，W

WFS 标签 PDF 中包含：

- WFS 箱标
- WFS 单号 / Shipment ID
- SKU 信息
- Box ID
- Quantity
- GTIN
- 可能包含 Pallet Label / 托盘标签

假设 WFS 标签一共有 `n + 1` 页，其中：

- `n` 页为有效箱标
- `1` 页为托盘标签

托盘标签通常可能在最后一页，但不能依赖页面位置判断，必须通过 ZPL/TXT 文档识别。

### 2.3 WFS ZPL/TXT 文档

WFS ZPL/TXT 文档是 WFS 标签 PDF 的源信息文件。每张标签通常由一段 ZPL 表示：

```zpl
^XA
...
^XZ
```

系统应根据每个 `^XA ... ^XZ` 标签段解析：

- 标签页序号
- 是否为箱标
- 是否为托盘标签
- SKU
- Box ID
- Shipment ID
- GTIN
- Quantity
- Box 序号，例如 `BOX 1 OF 2`

ZPL/TXT 是本工具识别 WFS 标签信息的主要依据。

### 2.4 货代物流标签 PDF，L

货代物流标签 PDF 中仅包含物流相关信息，例如物流单号、渠道、箱号等。

关键特点：

- 不包含 SKU 信息
- 页数为 `n`
- `n = 发货箱数 = WFS 有效箱标数量`
- 需要按照 WFS 有效箱标顺序进行暗部分配

---

## 3. 页面上传设计

### 3.1 页面只保留 5 个上传窗口

页面上只保留 5 个上传窗口，每个窗口代表一组标签。

```text
第 1 组标签上传窗口
第 2 组标签上传窗口
第 3 组标签上传窗口
第 4 组标签上传窗口
第 5 组标签上传窗口
```

每个上传窗口允许一次性上传多个文件。

每个窗口内应包含 3 个文件：

```text
WFS 标签 PDF
WFS 标签 ZPL/TXT
货代物流标签 PDF
```

### 3.2 文件类型识别

系统不依赖上传框区分文件类型，而是根据文件名规则自动识别：

- 哪个是 WFS 标签 PDF
- 哪个是 WFS 标签 ZPL/TXT
- 哪个是货代物流标签 PDF

文件命名规则暂时待定，后续单独补充。

当前实现时应预留文件识别接口，例如：

```python
def classify_uploaded_files(files: list[UploadedFile]) -> LabelGroupFiles:
    pass
```

返回结构：

```python
@dataclass
class LabelGroupFiles:
    group_index: int
    wfs_pdf_path: str | None
    wfs_zpl_path: str | None
    logistics_pdf_path: str | None
```

### 3.3 空上传窗口处理

如果某个上传窗口没有上传任何文件，则直接跳过该组。

如果某个上传窗口上传了部分文件但不完整，则报错。

例如：

```text
第 2 组文件不完整：缺少 WFS ZPL/TXT 文件。
```

### 3.4 多文件重复识别报错

如果同一组内识别到多个同类型文件，应报错，不允许继续处理。

例如：

```text
第 1 组存在多个 WFS 标签 PDF，请检查文件名。
```

---

## 4. 用户可配置选项

页面需要提供以下处理选项：

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| WFS 标签重复次数 | 2 | 每个 WFS 箱标在最终输出中出现几次 |
| 货代标签插入份数 | 1 | 每个货代标签在对应 WFS 标签后插入几次，可选 1 或 2 |
| 是否忽略 Pallet Label | 是 | 必须通过 ZPL/TXT 判断 |
| 是否跨组合并相同 SKU | 是 | 相同 SKU 最终合并为一个 PDF |
| 是否输出汇总表 | 是 | 建议输出 summary.xlsx 或 summary.csv |
| 输出格式 | ZIP | 最终打包下载 |

---

## 5. 单组标签处理逻辑

每一组标签先独立处理。

### 5.1 输入

```text
WFS 标签 PDF
WFS 标签 ZPL/TXT
货代物流标签 PDF
```

### 5.2 解析 ZPL/TXT

按 `^XA ... ^XZ` 拆分每一张标签。

示例：

```zpl
^XA
...
^FD BOX 1 OF 2^FS
...
^FDSINGLE SKU:^FS
...
^FDSKU1^FS
...
^XZ
```

程序应将每段 ZPL 解析成标签对象。

建议数据结构：

```python
@dataclass
class WfsLabel:
    group_index: int
    zpl_index: int          # ZPL 标签顺序，从 1 开始
    pdf_page: int           # 对应 WFS PDF 页码，从 1 开始
    label_type: str         # "box" 或 "pallet" 或 "unknown"
    sku: str | None
    box_id: str | None
    shipment_id: str | None
    gtin: str | None
    quantity: int | None
    box_text: str | None    # 例如 "BOX 1 OF 2"
```

### 5.3 判断是否为托盘标签

不能默认最后一页是托盘标签，必须根据 ZPL/TXT 内容判断。

推荐判断逻辑：

```text
如果 ZPL 标签段包含 PALLET 或 PALLET 1 OF 1
并且不包含 SINGLE SKU
则判定为 Pallet Label
```

更强判断条件可以包括：

```text
包含 SHIPMENT ID BARCODE
包含 PALLET
不包含 SINGLE SKU
```

托盘标签：

- 不参与 WFS 按 SKU 拆分
- 不参与货代标签分配
- 不参与最终插入合并
- 可在 summary 中记录为 ignored

### 5.4 判断是否为有效箱标

推荐判断逻辑：

```text
包含 SINGLE SKU
并且能提取出 SKU
则判定为有效 WFS 箱标
```

有效箱标需要参与后续处理。

### 5.5 单组校验

每组必须执行以下校验。

#### 5.5.1 WFS PDF 页数与 ZPL 标签段数量一致

例如：

```text
WFS PDF 页数 = 4
ZPL 标签段数量 = 4
```

如果不一致，报错：

```text
第 1 组错误：WFS PDF 页数为 4，但 ZPL/TXT 解析出 3 个标签段。
```

#### 5.5.2 有效 WFS 箱标数量与货代标签页数一致

忽略 Pallet Label 后：

```text
有效 WFS 箱标数 = n
货代标签 PDF 页数 = n
```

如果不一致，报错：

```text
第 1 组错误：有效 WFS 箱标为 3 页，但货代标签为 2 页。
请检查货代标签是否缺页或 WFS 标签是否解析异常。
```

#### 5.5.3 SKU 必须可识别

每个有效箱标必须识别出 SKU。

如果无法识别，报错：

```text
第 1 组错误：WFS 第 2 页无法识别 SKU。
```

---

## 6. 货代标签分配逻辑

货代物流标签本身不包含 SKU，因此必须按照 WFS 有效箱标顺序进行暗部分配。

核心规则：

```text
第 1 张有效 WFS 箱标 -> 第 1 张货代标签
第 2 张有效 WFS 箱标 -> 第 2 张货代标签
第 3 张有效 WFS 箱标 -> 第 3 张货代标签
...
```

系统内部应先生成逐箱对应表，而不是先按 SKU 粗暴拆分。

建议数据结构：

```python
@dataclass
class BoxPair:
    group_index: int
    box_index: int              # 当前组内有效箱序号，从 1 开始
    sku: str
    wfs_pdf_page: int
    logistics_pdf_page: int
    wfs_label: WfsLabel
```

示例：

```text
WFS 标签：W1 W2 W3 W4
ZPL 解析：W1-SKU1, W2-SKU1, W3-SKU2, W4-Pallet
货代标签：L1 L2 L3
```

有效箱标与货代标签分配结果：

| box_index | WFS 页 | SKU | 货代页 |
|---:|---:|---|---:|
| 1 | W1 | SKU1 | L1 |
| 2 | W2 | SKU1 | L2 |
| 3 | W3 | SKU2 | L3 |

---

## 7. 单组内按 SKU 生成临时结果

在每一组内部，按 SKU 对 `BoxPair` 分组。

示例：

```text
SKU1: (W1, L1), (W2, L2)
SKU2: (W3, L3)
```

默认输出规则：

```text
WFS 标签重复 2 次
货代标签插入 1 次
```

即每个箱子的页面顺序为：

```text
W W L
```

如果用户选择货代标签双份，则每个箱子的页面顺序为：

```text
W W L L
```

更通用的参数化写法：

```python
wfs_repeat = 2
logistics_repeat = 1  # 或 2
```

每个箱子的输出逻辑：

```python
for pair in sku_pairs:
    add_page(wfs_pdf, pair.wfs_pdf_page, repeat=wfs_repeat)
    add_page(logistics_pdf, pair.logistics_pdf_page, repeat=logistics_repeat)
```

### 7.1 示例

输入：

```text
WFS 标签：W1 W2 W3 W4
ZPL/TXT 解析：W1-SKU1, W2-SKU1, W3-SKU2, W4-Pallet
货代标签：L1 L2 L3
```

默认模式：

```text
SKU1 临时 PDF = W1 W1 L1 W2 W2 L2
SKU2 临时 PDF = W3 W3 L3
```

货代双份模式：

```text
SKU1 临时 PDF = W1 W1 L1 L1 W2 W2 L2 L2
SKU2 临时 PDF = W3 W3 L3 L3
```

---

## 8. 多组标签批处理逻辑

系统最多处理 5 组标签。

每组先独立完成：

```text
解析
校验
货代分配
按 SKU 生成组内临时 PDF
```

然后进入跨组汇总。

### 8.1 跨组同 SKU 合并

相同 SKU 的文档最终合并为一个 PDF。

合并规则：

```text
同 SKU 下，按照上传窗口组号顺序简单追加合并。
不能打乱每个 PDF 内部标签顺序。
不能重新排序箱标。
不能跨组重新分配货代标签。
```

示例：

```text
第 1 组：
SKU1 = W1 W1 L1 W2 W2 L2
SKU2 = W3 W3 L3

第 2 组：
SKU1 = W1 W1 L1
SKU3 = W2 W2 L2

第 3 组：
SKU2 = W1 W1 L1
```

最终输出：

```text
SKU1.pdf = 第1组SKU1内容 + 第2组SKU1内容
SKU2.pdf = 第1组SKU2内容 + 第3组SKU2内容
SKU3.pdf = 第2组SKU3内容
```

展开后：

```text
SKU1.pdf = W1 W1 L1 W2 W2 L2 W1 W1 L1
SKU2.pdf = W3 W3 L3 W1 W1 L1
SKU3.pdf = W2 W2 L2
```

注意：第二组里的 `W1/L1` 是第二组自己的页面，不是第一组页面。

---

## 9. 输出文件

最终输出应为 ZIP 包。

建议结构：

```text
output.zip
  SKU1.pdf
  SKU2.pdf
  SKU3.pdf
  summary.xlsx
  processing_log.txt
```

### 9.1 PDF 命名

PDF 文件名应基于 SKU。

注意需要清洗非法文件名字符：

```text
/ \ : * ? " < > |
```

示例：

```python
def safe_filename(name: str) -> str:
    pass
```

如果 SKU 为空或异常，不允许生成，必须报错。

### 9.2 汇总表

建议输出 `summary.xlsx` 或 `summary.csv`。

字段建议：

| 字段 | 说明 |
|---|---|
| job_id | 当前处理任务 ID |
| group_index | 第几组标签 |
| box_index | 当前组内第几个有效箱 |
| sku | SKU |
| wfs_pdf_file | WFS PDF 文件名 |
| wfs_pdf_page | WFS PDF 页码 |
| logistics_pdf_file | 货代 PDF 文件名 |
| logistics_pdf_page | 货代 PDF 页码 |
| quantity | WFS 箱标数量 |
| box_id | WFS Box ID |
| shipment_id | WFS Shipment ID |
| gtin | GTIN |
| output_pdf | 最终输出 PDF |
| status | processed / ignored_pallet / error |

### 9.3 处理日志

建议输出 `processing_log.txt`，记录：

- 每组上传文件识别结果
- 每组 PDF 页数
- ZPL 标签段数量
- Pallet Label 页码
- 有效箱标数量
- 货代标签页数
- 每个 SKU 输出页数
- 报错信息

---

## 10. 数据库与临时文件设计

### 10.1 每次处理生成唯一 job_id

每次用户点击处理时生成一个唯一任务 ID：

```text
job_id = 日期时间 + 随机字符串
```

示例：

```text
20260702_152233_a8f3
```

所有文件和数据库记录都必须绑定该 `job_id`。

### 10.2 临时目录结构

建议：

```text
/tmp/label_jobs/{job_id}/
  uploads/
    group_1/
      ...
    group_2/
      ...
  temp/
    group_outputs/
  output/
    SKU1.pdf
    SKU2.pdf
    summary.xlsx
    processing_log.txt
    output.zip
```

### 10.3 数据库表建议

可以先用 SQLite，后续再换 PostgreSQL。

#### jobs

| 字段 | 类型 |
|---|---|
| id | string |
| status | string |
| created_at | datetime |
| finished_at | datetime |
| error_message | text |

#### uploaded_files

| 字段 | 类型 |
|---|---|
| id | string |
| job_id | string |
| group_index | int |
| file_type | string |
| original_filename | string |
| stored_path | string |

#### parsed_labels

| 字段 | 类型 |
|---|---|
| id | string |
| job_id | string |
| group_index | int |
| pdf_page | int |
| label_type | string |
| sku | string |
| box_id | string |
| shipment_id | string |
| gtin | string |
| quantity | int |
| raw_zpl | text |

#### box_pairs

| 字段 | 类型 |
|---|---|
| id | string |
| job_id | string |
| group_index | int |
| box_index | int |
| sku | string |
| wfs_pdf_page | int |
| logistics_pdf_page | int |

---

## 11. 清理机制

### 11.1 输出完成后清理

用户输出完成后，需要执行一次清理，避免残余文档或数据库记录影响下次生产。

清理内容包括：

```text
1. 删除当前 job_id 对应的上传原文件
2. 删除当前 job_id 对应的临时 PDF
3. 删除当前 job_id 对应的中间解析数据
4. 删除当前 job_id 对应的数据库临时记录
```

### 11.2 是否保留最终 ZIP

根据业务需要选择：

方案 A：处理完成后保留最终 ZIP 一段时间。

```text
保留 output.zip 30 分钟
30 分钟后自动删除
```

方案 B：用户下载完成后立即删除。

```text
用户成功下载 output.zip 后立即删除整个 job_id 目录
```

推荐实现：

```text
先保留 30 分钟，定时任务清理过期 job。
```

### 11.3 清理不能影响其他任务

清理必须按 `job_id` 执行，禁止全局删除。

正确：

```python
cleanup_job(job_id)
```

错误：

```python
delete_all_temp_files()
```

---

## 12. 关键实现模块

建议拆成以下模块：

```text
app/
  main.py
  services/
    file_classifier.py
    zpl_parser.py
    pdf_processor.py
    job_processor.py
    output_builder.py
    cleanup.py
  models/
    schemas.py
  utils/
    filename.py
    validation.py
```

### 12.1 file_classifier.py

负责根据文件名识别文件类型。

待实现点：

```text
文件命名规则暂定，后续补充。
```

接口建议：

```python
def classify_group_files(group_index: int, files: list[UploadedFile]) -> LabelGroupFiles:
    pass
```

### 12.2 zpl_parser.py

负责解析 ZPL/TXT。

功能：

- 按 `^XA ... ^XZ` 拆分标签段
- 判断标签类型
- 提取 SKU
- 提取 Box ID
- 提取 Shipment ID
- 提取 GTIN
- 提取 Quantity
- 提取 Box 1 of N

接口建议：

```python
def parse_wfs_zpl(zpl_text: str, group_index: int) -> list[WfsLabel]:
    pass
```

### 12.3 pdf_processor.py

负责 PDF 页面处理。

功能：

- 获取 PDF 页数
- 抽取指定页
- 重复页面
- 插入页面
- 合并 PDF
- 输出 PDF

接口建议：

```python
def get_pdf_page_count(pdf_path: str) -> int:
    pass

def build_sku_pdf(
    sku: str,
    pairs: list[BoxPair],
    wfs_pdf_path: str,
    logistics_pdf_path: str,
    wfs_repeat: int,
    logistics_repeat: int,
    output_path: str,
) -> None:
    pass

def merge_pdfs(input_paths: list[str], output_path: str) -> None:
    pass
```

### 12.4 job_processor.py

负责总流程编排。

接口建议：

```python
def process_job(
    job_id: str,
    groups: list[LabelGroupFiles],
    options: ProcessingOptions,
) -> ProcessingResult:
    pass
```

### 12.5 output_builder.py

负责生成最终 ZIP、summary、log。

接口建议：

```python
def build_summary(rows: list[SummaryRow], output_path: str) -> None:
    pass

def build_zip(output_files: list[str], zip_path: str) -> None:
    pass
```

### 12.6 cleanup.py

负责清理任务数据。

接口建议：

```python
def cleanup_job(job_id: str, keep_output_zip: bool = True) -> None:
    pass
```

---

## 13. 推荐处理流程伪代码

```python
def process_job(job_id, uploaded_groups, options):
    all_group_sku_outputs = {}

    for group in uploaded_groups:
        if group.is_empty():
            continue

        files = classify_group_files(group.index, group.files)
        validate_group_files(files)

        wfs_page_count = get_pdf_page_count(files.wfs_pdf_path)
        logistics_page_count = get_pdf_page_count(files.logistics_pdf_path)

        zpl_text = read_text(files.wfs_zpl_path)
        labels = parse_wfs_zpl(zpl_text, group.index)

        validate_wfs_pdf_and_zpl_count(
            wfs_page_count=wfs_page_count,
            zpl_label_count=len(labels),
            group_index=group.index,
        )

        box_labels = [label for label in labels if label.label_type == "box"]
        pallet_labels = [label for label in labels if label.label_type == "pallet"]

        validate_logistics_count(
            box_count=len(box_labels),
            logistics_page_count=logistics_page_count,
            group_index=group.index,
        )

        pairs = []
        for i, label in enumerate(box_labels, start=1):
            pairs.append(BoxPair(
                group_index=group.index,
                box_index=i,
                sku=label.sku,
                wfs_pdf_page=label.pdf_page,
                logistics_pdf_page=i,
                wfs_label=label,
            ))

        group_sku_map = group_pairs_by_sku(pairs)

        for sku, sku_pairs in group_sku_map.items():
            temp_pdf_path = build_temp_path(job_id, group.index, sku)

            build_sku_pdf(
                sku=sku,
                pairs=sku_pairs,
                wfs_pdf_path=files.wfs_pdf_path,
                logistics_pdf_path=files.logistics_pdf_path,
                wfs_repeat=options.wfs_repeat,
                logistics_repeat=options.logistics_repeat,
                output_path=temp_pdf_path,
            )

            all_group_sku_outputs.setdefault(sku, []).append({
                "group_index": group.index,
                "path": temp_pdf_path,
            })

    final_outputs = []

    for sku, items in all_group_sku_outputs.items():
        items = sorted(items, key=lambda x: x["group_index"])

        input_paths = [item["path"] for item in items]
        output_path = build_final_output_path(job_id, sku)

        merge_pdfs(input_paths, output_path)
        final_outputs.append(output_path)

    summary_path = build_summary(...)
    log_path = build_processing_log(...)
    zip_path = build_zip(final_outputs + [summary_path, log_path])

    cleanup_job(job_id, keep_output_zip=True)

    return zip_path
```

---

## 14. 必须遵守的顺序规则

这是系统准确性的核心。

### 14.1 单组内部顺序

单组内部，必须按 WFS 有效箱标顺序处理：

```text
WFS 第 1 个有效箱标
WFS 第 2 个有效箱标
WFS 第 3 个有效箱标
...
```

货代标签按相同顺序分配：

```text
第 1 个有效箱标 -> L1
第 2 个有效箱标 -> L2
第 3 个有效箱标 -> L3
```

### 14.2 单个 SKU 内顺序

同一组内同一 SKU 的多个箱标，按照它们在原 WFS PDF 中出现的顺序输出。

### 14.3 跨组合并顺序

跨组合并时，按照页面上传窗口顺序：

```text
第 1 组
第 2 组
第 3 组
第 4 组
第 5 组
```

相同 SKU 只做简单追加合并。

### 14.4 禁止行为

以下行为禁止：

```text
禁止按 SKU 字母顺序重排箱标
禁止按货代标签文字内容重排
禁止跨组重新分配货代标签
禁止把同 SKU 不同组的页面打散后重新排序
禁止默认最后一页就是 Pallet Label
```

---

## 15. 待补充事项

### 15.1 文件命名识别规则

当前待定。

后续需要补充：

```text
如何根据文件名判断 WFS PDF
如何根据文件名判断 WFS ZPL/TXT
如何根据文件名判断货代 PDF
同一上传窗口内是否允许子文件夹
是否强制文件名前缀一致
```

### 15.2 输出文件命名规则

当前建议使用 SKU 命名，但可后续补充：

```text
是否加日期
是否加货件号
是否加箱数
是否加组号
```

### 15.3 错误提示文案

需要后续统一。

---

## 16. 最小可行版本，MVP

建议第一版先实现：

```text
1. 页面 5 个上传窗口
2. 每个窗口支持上传 3 个文件
3. 文件名规则先写死或用临时规则
4. 解析 ZPL/TXT
5. 忽略 Pallet Label
6. 校验 WFS PDF 页数、ZPL 标签数、货代标签页数
7. 按 WFS 有效箱标顺序分配货代标签
8. WFS 标签固定重复 2 次
9. 货代标签支持 1 份 / 2 份
10. 相同 SKU 跨组简单合并
11. 输出 ZIP
12. 输出 summary.csv
13. 任务完成后按 job_id 清理临时文件
```

数据库可以在 MVP 阶段简化，甚至仅使用内存数据结构和 job 临时目录。等流程稳定后，再加入完整数据库记录。

---

## 17. 技术建议

### 17.1 后端

推荐：

```text
Python FastAPI
```

原因：

- 适合文件上传
- 适合 PDF 处理
- 适合 ZPL/TXT 解析
- 后续容易封装成 API

### 17.2 PDF 处理库

推荐优先级：

```text
pypdf
PyMuPDF
```

当前需求主要是页面抽取、复制、插入、合并，`pypdf` 足够。

### 17.3 前端

推荐：

```text
React / Next.js
```

页面只需 5 个上传区域和几个处理选项。

### 17.4 数据库

MVP：

```text
不强制数据库，使用 job_id + 临时目录即可
```

正式版：

```text
SQLite 或 PostgreSQL
```

### 17.5 汇总表

推荐：

```text
CSV 第一版
XLSX 第二版
```

---

## 18. 示例场景

### 18.1 单组示例

输入：

```text
WFS 标签 PDF：
W1 W2 W3 W4

ZPL/TXT 解析：
W1 - SKU1
W2 - SKU1
W3 - SKU2
W4 - Pallet Label

货代标签 PDF：
L1 L2 L3
```

默认模式，货代标签 1 份：

```text
SKU1.pdf = W1 W1 L1 W2 W2 L2
SKU2.pdf = W3 W3 L3
```

货代标签 2 份：

```text
SKU1.pdf = W1 W1 L1 L1 W2 W2 L2 L2
SKU2.pdf = W3 W3 L3 L3
```

### 18.2 多组示例

输入：

```text
第 1 组：
SKU1.pdf = W1 W1 L1 W2 W2 L2
SKU2.pdf = W3 W3 L3

第 2 组：
SKU1.pdf = W1 W1 L1
SKU3.pdf = W2 W2 L2

第 3 组：
SKU2.pdf = W1 W1 L1
```

最终输出：

```text
SKU1.pdf = 第1组SKU1.pdf + 第2组SKU1.pdf
SKU2.pdf = 第1组SKU2.pdf + 第3组SKU2.pdf
SKU3.pdf = 第2组SKU3.pdf
```

---

## 19. 总结

本工具的核心不是简单 PDF 拆分，而是基于 ZPL/TXT 的精准标签解析与多 PDF 顺序重组。

核心原则：

```text
ZPL/TXT 是识别依据
WFS PDF 是页面来源
货代 PDF 按有效 WFS 箱标顺序暗部分配
Pallet Label 必须通过 ZPL/TXT 判断并忽略
单组内部顺序不能打乱
跨组同 SKU 只能简单追加合并
任务完成后必须按 job_id 清理临时数据
```

---

# 20. 校验机制设计

## 20.1 校验机制原则

系统所有处理必须先建立逐箱对应表，再进行 SKU 分组和 PDF 输出。

任何影响以下内容的异常，都应作为强校验错误，中断处理：

```text
WFS 标签页码
SKU 识别
Pallet Label 判断
货代标签分配顺序
输出 PDF 页数
跨组同 SKU 合并顺序
```

任何不影响最终页面对应关系，但可能提示业务异常的情况，应作为弱校验写入：

```text
summary.xlsx / summary.csv
processing_log.txt
页面提示信息
```

所有输出 PDF 生成后，必须反向校验页数是否符合公式：

```text
输出页数 = SKU 箱数 × (WFS 标签重复次数 + 货代标签插入份数)
```

任务完成后，必须基于 `job_id` 清理上传文件、临时文件和数据库临时记录。禁止全局清理。

---

## 20.2 校验等级定义

校验分为三类。

### 20.2.1 强校验

强校验不通过时，必须停止处理，不允许继续生成 PDF。

适用场景：

```text
文件缺失
文件重复
PDF 无法读取
ZPL/TXT 无法解析
WFS PDF 页数与 ZPL 标签数量不一致
有效 WFS 箱标数与货代标签页数不一致
有效箱标无法识别 SKU
货代页重复分配或漏分配
输出 PDF 页数不符合预期
```

### 20.2.2 弱校验

弱校验不一定阻止处理，但应提示用户确认或写入日志。

适用场景：

```text
同一组出现多个 Shipment ID
同一组出现多个目的仓
某个 SKU 箱数异常偏多或偏少
货代标签页数非常大
识别到多个 Pallet Label，但业务未来可能允许多托盘
```

### 20.2.3 日志校验

日志校验不中断处理，但必须记录。

适用场景：

```text
ZPL 标签段顺序已与 WFS PDF 页码顺序绑定
Pallet Label 页码已忽略
每个 SKU 输出文件页数
每组有效箱标数量
每组货代标签数量
跨组同 SKU 合并顺序
```

---

## 20.3 上传文件完整性校验

### 20.3.1 每组文件数量校验

每个上传窗口代表一组标签。

每组理论上必须包含：

```text
1 个 WFS 标签 PDF
1 个 WFS ZPL/TXT
1 个货代物流标签 PDF
```

如果某组完全为空，直接跳过。

如果某组只上传了部分文件，应作为强校验错误。

错误示例：

```text
第 2 组文件不完整：缺少货代物流标签 PDF。
```

### 20.3.2 同类型文件重复校验

如果某一组内识别到多个同类型文件，应停止处理。

例如：

```text
第 1 组存在多个 WFS 标签 PDF：
- 01_WFS.pdf
- 01_WFS_copy.pdf

请删除重复文件后重新上传。
```

适用对象：

```text
多个 WFS 标签 PDF
多个 WFS ZPL/TXT
多个货代物流标签 PDF
```

### 20.3.3 文件扩展名校验

只允许以下扩展名：

```text
WFS 标签 PDF：.pdf
货代标签 PDF：.pdf
ZPL/TXT：.txt / .zpl
```

如果上传了非预期文件，例如：

```text
.docx
.xlsx
.jpg
.png
.csv
```

应报错。

### 20.3.4 文件可读取校验

上传后应立即尝试读取文件。

需要检查：

```text
PDF 是否能正常打开
PDF 是否有页数
PDF 是否被加密
ZPL/TXT 是否能正常读取文本
ZPL/TXT 是否为空
```

错误示例：

```text
第 3 组 WFS PDF 无法读取，文件可能损坏或被加密。
```

---

## 20.4 WFS PDF 与 ZPL/TXT 对齐校验

### 20.4.1 WFS PDF 页数必须等于 ZPL 标签段数量

ZPL/TXT 通常通过以下结构表示一张标签：

```zpl
^XA
...
^XZ
```

因此必须校验：

```text
WFS PDF 页数 = ZPL/TXT 中解析出的标签段数量
```

通过示例：

```text
WFS PDF = 4 页
ZPL/TXT = 4 段
```

错误示例：

```text
第 1 组错误：WFS PDF 页数为 4，但 ZPL/TXT 解析出 3 个标签段。
```

这是强校验。

### 20.4.2 ZPL 标签段完整性校验

每个标签段必须同时具备：

```text
^XA 开始
^XZ 结束
```

如果出现残缺段，应停止处理。

错误示例：

```text
第 1 组 ZPL/TXT 第 4 段标签不完整，缺少 ^XZ。
```

### 20.4.3 ZPL 与 PDF 页码顺序绑定记录

系统默认：

```text
ZPL 第 1 段 = WFS PDF 第 1 页
ZPL 第 2 段 = WFS PDF 第 2 页
ZPL 第 3 段 = WFS PDF 第 3 页
...
```

该规则无法单独从 PDF 内部完全验证，因此需要通过：

```text
WFS PDF 页数 = ZPL 标签段数量
ZPL 标签段完整
ZPL 标签结构正常
```

来保证可靠性。

处理日志中应记录：

```text
已按 ZPL 标签段顺序匹配 WFS PDF 页码。
```

---

## 20.5 Pallet Label 校验

### 20.5.1 Pallet Label 不能只按最后一页判断

不能默认最后一页就是 Pallet Label。

必须通过 ZPL/TXT 内容判断。

推荐判断规则：

```text
包含 PALLET
并且不包含 SINGLE SKU
```

更强判断规则：

```text
包含 PALLET
包含 SHIPMENT ID BARCODE
不包含 SINGLE SKU
```

识别到 Pallet Label 后，需要记录页码。

示例：

```text
第 1 组 Pallet Label：WFS 第 4 页，已忽略。
```

### 20.5.2 Pallet Label 数量校验

当前业务假设每组通常最多只有一个 Pallet Label。

建议第一版规则：

```text
0 个 Pallet Label：允许
1 个 Pallet Label：允许
超过 1 个 Pallet Label：强校验报错
```

错误示例：

```text
第 2 组识别到 2 个 Pallet Label，请确认 WFS 标签是否包含多个托盘。
```

如果未来需要支持多托盘，可将该项改为弱校验，并增加多托盘处理逻辑。

### 20.5.3 Pallet Label 不参与货代分配校验

程序必须确保：

```text
Pallet Label 不占用货代标签页码
Pallet Label 不参与 SKU 输出
Pallet Label 不进入最终 PDF
```

示例：

```text
WFS：W1 W2 W3 W4
W4 = Pallet

货代：L1 L2 L3

正确对应：
W1 -> L1
W2 -> L2
W3 -> L3
```

禁止出现：

```text
W4 -> L4
```

---

## 20.6 SKU 识别校验

### 20.6.1 每个有效箱标必须识别到 SKU

只要 ZPL 标签被判断为有效箱标，就必须提取到 SKU。

如果提取不到，必须停止处理。

错误示例：

```text
第 1 组 WFS 第 2 页为箱标，但未识别到 SKU。
```

### 20.6.2 SKU 格式校验

SKU 应满足以下基本条件：

```text
SKU 不能为空
SKU 不应包含换行
SKU 长度不能过短，例如小于 2
SKU 长度不能过长，例如超过 100
```

如果 SKU 用作文件名，需要清洗非法文件名字符：

```text
/ \ : * ? " < > |
```

示例：

```text
原始 SKU：P/kcup:white*2
清洗后：P-kcup-white-2
```

### 20.6.3 SKU 提取位置校验

ZPL 中通常存在：

```text
SINGLE SKU:
```

并且 SKU 通常位于其后的某个 `^FD...^FS` 字段中。

程序不应仅依赖固定行号或固定字符位置，而应基于相对规则提取。

如果 `SINGLE SKU` 后无法找到有效 SKU，应报错。

---

## 20.7 数量与页数校验

### 20.7.1 有效 WFS 箱标数必须等于货代标签页数

忽略 Pallet Label 后，必须满足：

```text
有效 WFS 箱标数量 = 货代标签 PDF 页数
```

错误示例：

```text
第 3 组错误：
WFS 有效箱标数量为 12，
但货代标签 PDF 为 11 页。
请检查是否漏了一张货代标签。
```

这是强校验。

### 20.7.2 每组至少有一个有效箱标

如果某组上传了文件，但解析后没有任何有效 WFS 箱标，应停止处理。

错误示例：

```text
第 4 组未识别到任何有效 WFS 箱标。
```

### 20.7.3 每个 SKU 的箱数统计校验

程序应统计每组每个 SKU 的箱数。

示例：

```text
第 1 组：
SKU1：2 箱
SKU2：1 箱
总有效箱数：3 箱
货代标签：3 页
```

需要校验：

```text
各 SKU 箱数之和 = 有效 WFS 箱标数
```

---

## 20.8 货代标签分配校验

### 20.8.1 货代标签只能按有效 WFS 顺序分配

正确流程必须是：

```text
先建立 WFS 有效箱标与货代标签的逐箱对应关系
再按 SKU 分组输出
```

禁止反过来：

```text
先按 SKU 拆分 WFS
再猜测货代标签分配
```

分配规则：

```text
第 1 个有效 WFS 箱标 -> L1
第 2 个有效 WFS 箱标 -> L2
第 3 个有效 WFS 箱标 -> L3
...
```

### 20.8.2 货代标签页不能重复分配或漏分配

必须校验：

```text
分配出去的货代页码数量 = 货代 PDF 总页数
分配出去的货代页码无重复
分配出去的货代页码覆盖 1 到 n
```

错误示例：

```text
L2 被分配了两次
L3 未被分配
```

出现此类情况必须停止处理。

---

## 20.9 输出顺序校验

### 20.9.1 单个箱子的页面顺序校验

默认模式：

```text
W W L
```

货代双份模式：

```text
W W L L
```

其中：

```text
W = WFS 标签页
L = 货代物流标签页
```

程序应将该逻辑封装成独立函数，避免在多个位置重复实现导致顺序不一致。

建议接口：

```python
def append_box_pages(writer, wfs_page, logistics_page, wfs_repeat, logistics_repeat):
    pass
```

### 20.9.2 同一 SKU 在同一组内的顺序校验

同一组内同一 SKU 的多个箱标，必须按照它们在 WFS PDF 中出现的顺序输出。

示例：

```text
WFS 顺序：
W1-SKU1
W2-SKU2
W3-SKU1
```

则 SKU1 输出必须是：

```text
W1 W1 L1 W3 W3 L3
```

不能变成：

```text
W3 W3 L3 W1 W1 L1
```

### 20.9.3 跨组合并顺序校验

相同 SKU 跨组合并时，必须按照上传窗口顺序：

```text
第 1 组 -> 第 2 组 -> 第 3 组 -> 第 4 组 -> 第 5 组
```

如果某些组没有该 SKU，则跳过，但顺序仍以组号为准。

示例：

```text
SKU1.pdf = 第1组SKU1 + 第3组SKU1 + 第5组SKU1
```

禁止按文件名、文件上传时间、SKU 字母顺序重新排列跨组内容。

---

## 20.10 输出文件校验

### 20.10.1 输出 PDF 页数校验

每个 SKU 的输出页数应符合公式：

```text
输出页数 = 该 SKU 箱数 × (WFS 重复次数 + 货代标签插入份数)
```

示例：

```text
SKU1 有 2 箱
WFS 重复次数 = 2
货代插入份数 = 1

输出页数 = 2 × (2 + 1) = 6 页
```

如果货代标签双份：

```text
输出页数 = 2 × (2 + 2) = 8 页
```

生成输出 PDF 后，应重新读取 PDF 页数并校验。

这是强校验。

### 20.10.2 最终 ZIP 内容校验

打包前检查：

```text
至少有一个 SKU PDF
summary 文件存在
processing_log 文件存在
ZIP 文件能正常生成
```

如果没有任何 SKU PDF，不允许生成空 ZIP。

### 20.10.3 输出文件名重复校验

如果不同 SKU 经过文件名清洗后变成相同文件名，需要避免覆盖。

示例：

```text
SKU A/B
SKU A:B
```

清洗后可能都变成：

```text
SKU A-B
```

处理方式：

```text
SKU A-B.pdf
SKU A-B_2.pdf
```

同时需要在 summary 中记录原始 SKU。

---

## 20.11 数据库与任务隔离校验

### 20.11.1 job_id 隔离校验

每次处理必须生成唯一 `job_id`。

以下所有内容都必须绑定当前 `job_id`：

```text
上传文件
临时文件
解析结果
输出文件
日志
summary
```

严禁跨 job 读取或复用文件。

### 20.11.2 清理范围校验

清理时只能清理当前任务：

```python
cleanup_job(job_id)
```

禁止全局删除：

```python
delete_all_temp_files()
```

清理前应检查路径中是否包含当前 `job_id`，防止误删。

### 20.11.3 任务完成后残留检查

处理完成后执行残留检查：

```text
检查当前 job_id 的 uploads 目录是否已删除
检查当前 job_id 的 temp 目录是否已删除
检查当前 job_id 的数据库临时记录是否已删除
```

如果选择保留最终下载文件，则只保留：

```text
output.zip
```

或者只保留：

```text
output/
```

其他中间文件全部清理。

---

## 20.12 用户确认型校验

### 20.12.1 SKU 箱数异常提示

如果某个 SKU 箱数明显异常，例如某组中某个 SKU 箱数过多或过少，可以写入弱校验提示。

示例：

```text
第 1 组 SKU-FBA-001 共 1 箱。
第 2 组 SKU-FBA-001 共 25 箱。
```

该情况不一定错误，但应记录。

### 20.12.2 多个仓库或多个 Shipment ID 提示

如果同一组中出现多个 Shipment ID 或多个 Ship To 仓库，建议提示用户确认。

示例：

```text
第 1 组识别到多个 Shipment ID：
- 9233759WFA
- 9233760WFA

请确认该组是否确实包含多个货件。
```

该项可作为弱校验。

### 20.12.3 货代标签页数过大提示

如果货代标签页数超过阈值，例如 200 页，可以提示用户确认，避免误传大文件。

---

## 20.13 处理前预览确认

建议在正式生成 PDF 前，先展示预览表。

示例：

| 组号 | 有效箱序 | WFS 页 | SKU | 货代页 | 输出顺序 |
|---:|---:|---:|---|---:|---|
| 1 | 1 | 1 | SKU1 | 1 | W1 W1 L1 |
| 1 | 2 | 2 | SKU1 | 2 | W2 W2 L2 |
| 1 | 3 | 3 | SKU2 | 3 | W3 W3 L3 |
| 2 | 1 | 1 | SKU1 | 1 | W1 W1 L1 |

用户确认后再正式生成 PDF。

这一步可以显著降低贴错标签的风险。

---

## 20.14 MVP 阶段必须实现的强校验

第一版至少实现以下 12 条强校验：

```text
1. 每组文件完整性校验
2. 同类型文件重复校验
3. PDF 可读取校验
4. ZPL/TXT 可读取校验
5. WFS PDF 页数 = ZPL 标签段数量
6. 有效 WFS 箱标数 = 货代标签页数
7. 每个有效箱标必须识别 SKU
8. Pallet Label 必须被排除
9. 货代页不能重复分配、不能漏分配
10. 输出 PDF 页数公式校验
11. 跨组同 SKU 合并顺序校验
12. job_id 清理范围校验
```

---

## 20.15 建议测试用例

### 20.15.1 正常单组

```text
WFS：W1-SKU1, W2-SKU1, W3-SKU2, W4-Pallet
货代：L1, L2, L3
输出：
SKU1 = W1 W1 L1 W2 W2 L2
SKU2 = W3 W3 L3
```

### 20.15.2 货代标签双份

```text
WFS：W1-SKU1, W2-SKU2, W3-Pallet
货代：L1, L2
输出：
SKU1 = W1 W1 L1 L1
SKU2 = W2 W2 L2 L2
```

### 20.15.3 有效箱标数与货代页数不一致

```text
WFS 有效箱标：3
货代标签页数：2
预期：报错，中断处理
```

### 20.15.4 ZPL 标签段数量与 WFS PDF 页数不一致

```text
WFS PDF：4 页
ZPL 标签段：3 段
预期：报错，中断处理
```

### 20.15.5 同 SKU 跨组合并

```text
第 1 组 SKU1 = A1 A1 L1
第 3 组 SKU1 = C1 C1 L1

最终：
SKU1 = 第1组内容 + 第3组内容
```

### 20.15.6 Pallet Label 不在最后一页

```text
WFS：W1-SKU1, W2-Pallet, W3-SKU2
货代：L1, L2
预期：
W1 -> L1
W3 -> L2
Pallet 被忽略
```

### 20.15.7 SKU 文件名清洗冲突

```text
SKU A/B
SKU A:B

预期：
不能覆盖输出文件
summary 中保留原始 SKU
```
