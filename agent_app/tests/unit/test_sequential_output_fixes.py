from pathlib import Path
from types import SimpleNamespace
import types
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

multi_agent_root = Path(__file__).resolve().parents[2] / "agent_server" / "multi_agent"
multi_agent_pkg = types.ModuleType("agent_server.multi_agent")
multi_agent_pkg.__path__ = [str(multi_agent_root)]
sys.modules.setdefault("agent_server.multi_agent", multi_agent_pkg)

core_pkg = types.ModuleType("agent_server.multi_agent.core")
core_pkg.__path__ = [str(multi_agent_root / "core")]
sys.modules.setdefault("agent_server.multi_agent.core", core_pkg)

agents_pkg = types.ModuleType("agent_server.multi_agent.agents")
agents_pkg.__path__ = [str(multi_agent_root / "agents")]
sys.modules.setdefault("agent_server.multi_agent.agents", agents_pkg)

langchain_core_pkg = types.ModuleType("langchain_core")
sys.modules.setdefault("langchain_core", langchain_core_pkg)

runnables_stub = types.ModuleType("langchain_core.runnables")
runnables_stub.Runnable = object
sys.modules.setdefault("langchain_core.runnables", runnables_stub)

messages_stub = types.ModuleType("langchain_core.messages")
messages_stub.AIMessage = SimpleNamespace
messages_stub.HumanMessage = SimpleNamespace
messages_stub.SystemMessage = SimpleNamespace
sys.modules.setdefault("langchain_core.messages", messages_stub)

langgraph_pkg = types.ModuleType("langgraph")
sys.modules.setdefault("langgraph", langgraph_pkg)

langgraph_config_stub = types.ModuleType("langgraph.config")
langgraph_config_stub.get_stream_writer = lambda: (lambda *_args, **_kwargs: None)
sys.modules.setdefault("langgraph.config", langgraph_config_stub)

graph_stub = types.ModuleType("agent_server.multi_agent.core.graph")
graph_stub.create_super_agent_hybrid = lambda *args, **kwargs: None
graph_stub.create_agent_graph = lambda *args, **kwargs: None
sys.modules.setdefault("agent_server.multi_agent.core.graph", graph_stub)

from agent_server.multi_agent.agents.chart_generator import ChartGenerator
from agent_server.multi_agent.agents.sql_execution import _append_remaining_skipped_artifacts
from agent_server.multi_agent.agents.summarize import _build_artifact_entries
from agent_server.multi_agent.agents.summarize_agent import ResultSummarizeAgent
from agent_server.multi_agent.tools.web_search import detect_code_columns


class StubLlm:
    def __init__(self, content: str):
        self._content = content

    def invoke(self, _prompt: str):
        return SimpleNamespace(content=self._content)


def test_build_artifact_entries_prefers_execution_result_metadata():
    state = {
        "execution_results": [
            {
                "success": True,
                "sql": "SELECT 1",
                "query_label": "Top 10 members",
                "columns": ["patient_id"],
                "result": [{"patient_id": "a"}],
                "row_count": 1,
            },
            {
                "success": True,
                "sql": "SELECT 2",
                "query_label": "Coverage details",
                "columns": ["benefit_type"],
                "result": [{"benefit_type": "MEDICAL"}],
                "row_count": 1,
            },
        ],
        "sql_queries": ["STALE QUERY"],
        "sql_query_labels": ["Stale label"],
    }

    entries = _build_artifact_entries(state)

    assert [entry["label"] for entry in entries] == [
        "Top 10 members",
        "Coverage details",
    ]
    assert [entry["sql"] for entry in entries] == ["SELECT 1", "SELECT 2"]


def test_append_remaining_skipped_artifacts_pads_sequential_results():
    state = {
        "total_sub_questions": 5,
        "sub_questions": [
            "Cost breakdown",
            "Utilization",
            "Comorbidities",
            "Demographics",
            "Coverage details",
        ],
    }
    preserved = [
        {
            "status": "success",
            "success": True,
            "query_number": 1,
            "query_label": "Cost breakdown",
            "sql": "SELECT 1",
            "columns": ["patient_id"],
            "result": [{"patient_id": "a"}],
            "row_count": 1,
        },
        {
            "status": "success",
            "success": True,
            "query_number": 2,
            "query_label": "Utilization",
            "sql": "SELECT 2",
            "columns": ["patient_id"],
            "result": [{"patient_id": "a"}],
            "row_count": 1,
        },
        {
            "status": "success",
            "success": True,
            "query_number": 3,
            "query_label": "Comorbidities",
            "sql": "SELECT 3",
            "columns": ["patient_id"],
            "result": [{"patient_id": "a"}],
            "row_count": 1,
        },
        {
            "status": "success",
            "success": True,
            "query_number": 4,
            "query_label": "Demographics",
            "sql": "SELECT 4",
            "columns": ["patient_id"],
            "result": [{"patient_id": "a"}],
            "row_count": 1,
        },
    ]

    padded = _append_remaining_skipped_artifacts(
        state,
        preserved,
        start_step=4,
        reason="Skipped because already covered by prior results.",
    )

    assert len(padded) == 5
    assert padded[-1]["status"] == "skipped"
    assert padded[-1]["query_number"] == 5
    assert padded[-1]["query_label"] == "Coverage details"
    assert "already covered" in padded[-1]["skip_reason"]


def test_summary_prompt_requires_per_result_sections_and_safe_inference():
    agent = ResultSummarizeAgent(llm=None)  # type: ignore[arg-type]

    prompt = agent._build_summary_prompt(
        {
            "original_query": "Analyze top 10 most expensive members",
            "question_clear": True,
            "execution_results": [
                {
                    "success": True,
                    "query_label": "Cost breakdown",
                    "columns": ["patient_id", "total_cost"],
                    "result": [{"patient_id": "a", "total_cost": 10}],
                    "row_count": 1,
                },
                {
                    "success": True,
                    "query_label": "Coverage details",
                    "columns": ["patient_id", "benefit_type"],
                    "result": [{"patient_id": "a", "benefit_type": "MEDICAL"}],
                    "row_count": 1,
                },
            ],
        }
    )

    assert "create one `###` subsection per result set" in prompt
    assert "Do not merge multiple result sets into one markdown table" in prompt
    assert "do NOT infer distinct member counts" in prompt
    assert "Statements about how many charts" in prompt
    assert "Query 1 — Cost breakdown Result" in prompt
    assert "Query 2 — Coverage details Result" in prompt


def test_sql_sections_are_keyed_by_final_artifact_labels():
    artifact_entries = [
        {
            "label": "Cost breakdown",
            "status": "success",
            "sql": "SELECT 1",
            "sql_explanation": "Built from medical and pharmacy claims.",
        },
        {
            "label": "Coverage details",
            "status": "skipped",
            "sql": "",
            "skip_reason": "Skipped because already covered by demographics result.",
            "sql_explanation": "Skipped because already covered by demographics result.",
        },
    ]

    sql_block = ResultSummarizeAgent.format_sql_download(artifact_entries)
    explanation_block = ResultSummarizeAgent.format_sql_explanation(artifact_entries)

    assert "**Cost breakdown**" in sql_block
    assert "**Coverage details**" in sql_block
    assert "No SQL generated for this planned query" in sql_block

    assert "### Query 1 — Cost breakdown" in explanation_block
    assert "### Query 2 — Coverage details" in explanation_block
    assert "Skipped / already covered" in explanation_block


def test_chart_generator_dedupes_repeated_patient_totals():
    generator = ChartGenerator(llm=None)  # type: ignore[arg-type]

    chart_data, note = generator._agg_top_n(
        data=[
            {
                "patient_id": "a",
                "diagnosis_code": "D1",
                "total_paid_amount": 100.0,
            },
            {
                "patient_id": "a",
                "diagnosis_code": "D2",
                "total_paid_amount": 100.0,
            },
            {
                "patient_id": "b",
                "diagnosis_code": "D3",
                "total_paid_amount": 50.0,
            },
        ],
        x_field="patient_id",
        metric="total_paid_amount",
        series=[{"field": "total_paid_amount", "name": "Total Paid", "format": "currency"}],
        n=10,
        other_label="Other",
        result_context={
            "label": "Comorbidities",
            "row_grain_hint": "Rows are diagnosis-level detail.",
        },
    )

    assert chart_data == [
        {"patient_id": "a", "total_paid_amount": 100.0},
        {"patient_id": "b", "total_paid_amount": 50.0},
    ]
    assert "guardrail" in note


def test_detect_code_columns_skips_aggregate_metric_columns():
    llm = StubLlm(
        '[{"column":"distinct_cpt_codes","code_type":"CPT"},'
        '{"column":"diagnosis_code","code_type":"ICD10"}]'
    )

    detected = detect_code_columns(
        columns=["distinct_cpt_codes", "diagnosis_code"],
        sample_data=[
            {"distinct_cpt_codes": 578, "diagnosis_code": "C641"},
            {"distinct_cpt_codes": 223, "diagnosis_code": "I10"},
        ],
        llm=llm,
    )

    assert detected == [{"column": "diagnosis_code", "code_type": "ICD10"}]
