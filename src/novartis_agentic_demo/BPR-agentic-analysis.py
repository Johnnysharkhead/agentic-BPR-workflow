import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from novartis_agentic_demo.llm_config import LLMConfig


class DeviationState(TypedDict, total=False):
    batch_record: dict
    deviations: list
    severity: str
    recommendation: dict   # structured: summary, immediate_correction, root_cause_analysis, preventive_actions
    human_approved: bool
    final_action: str


if not LLMConfig.api_key:
    raise RuntimeError("请先设置 API_KEY 或 OPENAI_API_KEY 环境变量，然后再运行真实 LLM。")

llm = LLMConfig.get_llm()


def invoke_llm(prompt: str) -> str:
    result = llm.invoke(prompt)
    return getattr(result, "content", str(result))


def _parse_json_response(content: str) -> dict:
    content = content.strip()
    if content.startswith("```json"):
        content = content.removeprefix("```json").removesuffix("```").strip()
    elif content.startswith("```"):
        content = content.removeprefix("```").removesuffix("```").strip()
    parsed, _ = json.JSONDecoder().raw_decode(content)
    return parsed


# Node 1: Detect deviations
def detect_deviations(state: DeviationState):
    prompt = f"""
    你是制药工厂 QA 专家。分析以下批生产记录，识别偏差：

    {state['batch_record']}

    返回 JSON：{{"deviations": [...], "severity": "Minor/Major/Critical"}}
    """
    content = invoke_llm(prompt)
    parsed = _parse_json_response(content)
    return {
        "deviations": parsed.get("deviations", []),
        "severity": parsed.get("severity", "Minor"),
    }


# Node 2: Generate structured CAPA recommendation
def generate_recommendation(state: DeviationState):
    prompt = f"""
你是制药工厂 QA 专家。根据以下偏差，给出结构化的 CAPA 建议。

偏差列表：{json.dumps(state['deviations'], ensure_ascii=False)}
严重程度：{state['severity']}

返回如下 JSON 结构，所有文字使用中文：
{{
    "deviation_cn": "一句话概括本次偏差的核心问题，供 SharePoint 列表展示。",
    "summary": "用 --> 符号连接的推理链，格式固定为五段，纯文本仅用 --> 分隔，不加序号或换行：偏差定性与{state['severity']}级别依据 --> 具体质量或患者安全风险 --> 关键立即行动及原因 --> 针对根本原因的纠正措施 --> 预防复发的关键措施。",
    "immediate_correction": [
        "立即行动1",
        "立即行动2"
    ],
    "root_cause_analysis": [
        "潜在根本原因1",
        "潜在根本原因2"
    ],
    "preventive_actions": [
        "预防措施1",
        "预防措施2"
    ]
}}
"""
    content = invoke_llm(prompt)
    try:
        parsed = _parse_json_response(content)
    except Exception:
        parsed = {
            "deviation_cn": "",
            "summary": content[:500],
            "immediate_correction": [],
            "root_cause_analysis": [],
            "preventive_actions": [],
        }
    return {"recommendation": parsed}


# Node 3: HITL pause for Major/Critical deviations
def human_review(state: DeviationState):
    decision = interrupt({
        "message": "AI identified a Major/Critical deviation. Please review the recommendation and decide whether to trigger CAPA:",
        "deviations": state["deviations"],
        "recommendation": state["recommendation"],
    })
    return {"human_approved": decision == "approve"}


# Node 4: Execute final action
def execute_action(state: DeviationState):
    if not state.get("deviations"):
        return {"final_action": "无偏差，批记录已归档"}
    if state.get("severity") == "Minor" or state.get("human_approved"):
        return {"final_action": "偏差报告已归档"}
    return {"final_action": "人工审核拒绝，等待进一步指示"}


def route_after_detect(state: DeviationState):
    """Skip recommendation entirely when no deviations are found."""
    if not state.get("deviations"):
        return "execute"
    return "recommend"


def route_by_severity(state: DeviationState):
    if state["severity"] == "Minor":
        return "execute"
    return "human_review"


def build_graph():
    builder = StateGraph(DeviationState)
    builder.add_node("detect", detect_deviations)
    builder.add_node("recommend", generate_recommendation)
    builder.add_node("human_review", human_review)
    builder.add_node("execute", execute_action)

    builder.set_entry_point("detect")
    builder.add_conditional_edges("detect", route_after_detect, {
        "recommend": "recommend",
        "execute": "execute",
    })
    builder.add_conditional_edges("recommend", route_by_severity, {
        "human_review": "human_review",
        "execute": "execute",
    })
    builder.add_edge("human_review", "execute")
    builder.add_edge("execute", END)

    return builder.compile(checkpointer=MemorySaver())


graph = build_graph()

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
OUTPUT_FILE = OUTPUT_DIR / "bpr_agentic_analysis_results.json"


MOCK_BATCH_RECORDS = [
    {
        "batch_id": "BATCH-001",
        "product": "Demo tablet 50 mg",
        "process_step": "Cold-chain storage before packaging",
        "observation": "Temperature reached 9 C for 4 minutes; limit is 2-8 C.",
        "expected_severity": "Minor",
    },
    {
        "batch_id": "BATCH-002",
        "product": "Demo injectable 10 mg/mL",
        "process_step": "Sterile filtration",
        "observation": "Filter integrity post-use bubble point failed. No replacement filter record found.",
        "expected_severity": "Critical",
    },
    {
        "batch_id": "BATCH-003",
        "product": "Demo capsule 25 mg",
        "process_step": "Blending",
        "observation": "Blend time was 42 minutes instead of approved range 45-60 minutes. Operator noted line clearance was completed.",
        "expected_severity": "Major",
    },
    {
        "batch_id": "BATCH-004",
        "product": "Demo tablet 100 mg",
        "process_step": "Compression",
        "observation": "2 out of 20 sampled tablets showed hardness of 3.8 kP, marginally below the lower spec limit of 4.0 kP. All other attributes (weight, thickness, friability) were within specification. The deviation was detected during in-process checks and the compression force was adjusted immediately.",
        "expected_severity": "Minor",
    },
    {
        "batch_id": "BATCH-005",
        "product": "Demo oral suspension",
        "process_step": "Packaging",
        "observation": "Line clearance checklist is missing supervisor signature. No mix-up observed in reconciliation records.",
        "expected_severity": "Major",
    },
]


def format_interrupts(interrupt_payload) -> list[dict]:
    if not interrupt_payload:
        return []

    interrupts = interrupt_payload
    if not isinstance(interrupts, list):
        interrupts = [interrupts]

    formatted = []
    for item in interrupts:
        value = getattr(item, "value", item)
        if not isinstance(value, dict):
            value = {"raw": str(value)}

        formatted.append({
            "id": getattr(item, "id", None),
            "message": value.get("message"),
            "deviations": value.get("deviations", []),
            "recommendation": value.get("recommendation"),
        })

    return formatted


def _build_title(batch_id: str, process_step: str, severity: str) -> str:
    return f"{batch_id} | {process_step} | {severity} Deviation"


def format_batch_result(index: int, batch_record: dict, result: dict) -> dict:
    """
    Output schema per batch:

    sharepoint_item          ← Direct SharePoint list import fields
    ├── Title                    "{BatchID} | {ProcessStep} | {Severity} Deviation"
    ├── BatchID                  e.g. "BATCH-001"
    ├── Severity                 "Minor" | "Major" | "Critical"
    ├── Deviation                中文一句话偏差描述
    └── Recommendation           中文推理链，用 --> 连接

    details                  ← Full analysis for audit trail / downstream use
    ├── sequence
    ├── product
    ├── process_step
    ├── observation
    ├── expected_severity
    ├── analysis_status          "completed" | "pending_human_review"
    ├── deviations[]
    ├── capa
    │   ├── immediate_correction[]
    │   ├── root_cause_analysis[]
    │   └── preventive_actions[]
    ├── human_review
    │   ├── required
    │   ├── approved
    │   └── requests[]
    ├── final_action
    └── generated_at
    """
    interrupt_requests = format_interrupts(result.get("__interrupt__"))
    analysis_status = "pending_human_review" if interrupt_requests else "completed"

    recommendation = result.get("recommendation") or {}
    batch_id = batch_record.get("batch_id", "")
    severity = result.get("severity", "")
    process_step = batch_record.get("process_step", "")
    deviations = result.get("deviations", [])
    no_deviation = len(deviations) == 0

    return {
        "sharepoint_item": {
            "Title": _build_title(batch_id, process_step, severity),
            "BatchID": batch_id,
            "Severity": severity,
            "Deviation": "无偏差，各项指标均符合规格要求。" if no_deviation else recommendation.get("deviation_cn", ""),
            "Recommendation": "无需采取纠偏措施。" if no_deviation else recommendation.get("summary", ""),
        },
        "details": {
            "sequence": index,
            "product": batch_record.get("product"),
            "process_step": process_step,
            "observation": batch_record.get("observation"),
            "expected_severity": batch_record.get("expected_severity"),
            "analysis_status": analysis_status,
            "deviations": result.get("deviations", []),
            "capa": {
                "immediate_correction": recommendation.get("immediate_correction", []),
                "root_cause_analysis": recommendation.get("root_cause_analysis", []),
                "preventive_actions": recommendation.get("preventive_actions", []),
            },
            "human_review": {
                "required": analysis_status == "pending_human_review",
                "approved": result.get("human_approved"),
                "requests": interrupt_requests,
            },
            "final_action": result.get("final_action"),
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


def write_batch_result(batch_result: dict, output_dir: Path = OUTPUT_DIR) -> Path:
    """Save a single batch result to outputs/{BatchID}.json."""
    batch_id = batch_result["sharepoint_item"]["BatchID"]
    output_file = output_dir / f"{batch_id}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(batch_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_file


def write_analysis_report(results: list[dict], output_file: Path = OUTPUT_FILE) -> Path:
    """Save the consolidated report with a top-level sharepoint_items array for bulk import."""
    report = {
        "report_metadata": {
            "report_name": "BPR Agentic Deviation Analysis",
            "generated_at": datetime.now(UTC).isoformat(),
            "record_count": len(results),
            "completed_count": sum(
                1 for r in results if r["details"]["analysis_status"] == "completed"
            ),
            "pending_human_review_count": sum(
                1 for r in results if r["details"]["analysis_status"] == "pending_human_review"
            ),
        },
        "sharepoint_items": [r["sharepoint_item"] for r in results],
        "batch_results": results,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_file


if __name__ == "__main__":
    batch_results = []

    for index, batch_record in enumerate(MOCK_BATCH_RECORDS, start=1):
        print(f"\n=== {batch_record['batch_id']} ===")
        config = {"configurable": {"thread_id": f"demo-thread-{index}"}}
        result = graph.invoke({"batch_record": batch_record}, config=config)
        batch_result = format_batch_result(index, batch_record, result)
        batch_results.append(batch_result)

        batch_file = write_batch_result(batch_result)
        print(f"  → Saved: {batch_file}")

        if "__interrupt__" in result:
            print("  HITL interrupt pending — awaiting human review")
        else:
            print(f"  severity:  {result.get('severity')}")
            print(f"  status:    {batch_result['details']['analysis_status']}")
            print(f"  action:    {result.get('final_action')}")

    saved_path = write_analysis_report(batch_results)
    print(f"\nConsolidated report saved to: {saved_path}")
