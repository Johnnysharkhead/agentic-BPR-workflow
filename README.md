# BPR 偏差智能分析系统

基于 LangGraph 的制药批生产记录（BPR）偏差自动分析工具。输入批记录，自动识别偏差、评估严重程度、生成 CAPA 建议，结果可直接导入 SharePoint。

## 项目结构

```
src/novartis_agentic_demo/
├── BPR-agentic-analysis.py   # 主流程：偏差分析 + 结果输出
├── export_to_csv.py          # 将结果导出为 SharePoint 可导入的 CSV
├── sync_to_sharepoint.py     # 通过 Graph API 直接同步到 SharePoint（需认证）
└── llm_config.py             # LLM 配置

outputs/
├── BATCH-001.json            # 每个 Batch 的独立结果文件
├── ...
├── bpr_agentic_analysis_results.json   # 所有 Batch 的汇总报告
└── sharepoint_import.csv               # SharePoint 导入文件
```

## 环境准备

**1. 安装依赖**
```bash
uv sync
```

**2. 配置 API Key**

在项目根目录创建 `.env` 文件：
```
OPENAI_API_KEY=你的API密钥
```


## 使用方法

### 第一步：运行偏差分析

```bash
uv run python -m novartis_agentic_demo.BPR-agentic-analysis
```

每个 Batch 分析完成后自动保存到 `outputs/BATCH-XXX.json`。

**分析流程：**
```
输入批记录 → 识别偏差 → 评估严重程度
                              ├── Minor     → 直接生成建议 → 归档
                              └── Major/Critical → 人工审核（HITL）→ 归档
```

### 第二步：导出 CSV（用于 SharePoint 导入）

```bash
uv run python -m novartis_agentic_demo.export_to_csv
```

生成 `outputs/sharepoint_import.csv`，对应 SharePoint list 的五列：

| Title | BatchID | Severity | Deviation | Recommendation |
|-------|---------|----------|-----------|----------------|
| BATCH-001 \| Cold-chain... \| Minor Deviation | BATCH-001 | Minor | 一句话偏差描述 | 推理链（用 → 连接） |

**导入到 SharePoint：**
1. 用 Excel 打开 `sharepoint_import.csv`
2. 全选数据行（不含表头）→ 复制
3. 打开 SharePoint list → **Edit in grid view** → 粘贴

## 修改 Batch 数据

分析的输入数据在 `BPR-agentic-analysis.py` 的 `MOCK_BATCH_RECORDS` 列表中，每条记录格式：

```python
{
    "batch_id": "BATCH-001",
    "product": "产品名称",
    "process_step": "工序名称",
    "observation": "观察到的现象描述",
    "expected_severity": "Minor / Major / Critical",
}
```
