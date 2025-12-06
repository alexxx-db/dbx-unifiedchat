# Unity Catalog Functions Reference

Quick reference guide for the UC functions used in the multi-agent system.

## Functions Overview

| Function | Purpose | Input | Output |
|----------|---------|-------|--------|
| `analyze_query_plan` | Analyze query and create execution plan | Query text | JSON with plan details |
| `synthesize_sql_fast_route` | Generate SQL directly across tables | Query + table metadata | SQL query |
| `synthesize_sql_slow_route` | Combine multiple SQL queries | Query + sub-queries | Combined SQL |
| `execute_sql_query` | Execute SQL and format results | SQL query | JSON with results/errors |
| `get_table_metadata` | Get table schemas for spaces | Space IDs (JSON) | Table metadata (JSON) |
| `verbal_merge_results` | Merge narrative answers | Query + results (JSON) | Merged text response |

---

## Function Details

### 1. analyze_query_plan

**Full Name:** `yyang.multi_agent_genie.analyze_query_plan`

**Purpose:** Analyzes a user query to determine clarity, relevant Genie spaces, and execution strategy.

**Parameters:**
```python
query: str                      # Required: The user's question
vector_search_index: str        # Optional: Vector search index name
                               # Default: "yyang.multi_agent_genie.enriched_genie_docs_chunks_vs_index"
num_results: int               # Optional: Number of relevant spaces to find
                               # Default: 5
```

**Returns:** JSON string with structure:
```json
{
  "question_clear": true/false,
  "clarification_needed": "string (if question_clear=false)",
  "clarification_options": ["option1", "option2", ...],
  "sub_questions": ["sub-q1", "sub-q2", ...],
  "requires_multiple_spaces": true/false,
  "relevant_space_ids": ["space_id_1", "space_id_2", ...],
  "requires_join": true/false,
  "join_strategy": "fast_route" | "slow_route" | null,
  "execution_plan": "description of execution strategy"
}
```

**Example Usage:**
```python
from databricks_langchain import UCFunctionToolkit

toolkit = UCFunctionToolkit(
    function_names=["yyang.multi_agent_genie.analyze_query_plan"]
)
tool = toolkit.tools[0]

result = tool.invoke({
    "query": "How many Medicare patients had claims in 2024?"
})
```

**SQL Usage:**
```sql
SELECT yyang.multi_agent_genie.analyze_query_plan(
  'How many Medicare patients had claims in 2024?',
  'yyang.multi_agent_genie.enriched_genie_docs_chunks_vs_index',
  5
);
```

---

### 2. synthesize_sql_fast_route

**Full Name:** `yyang.multi_agent_genie.synthesize_sql_fast_route`

**Purpose:** Directly generate SQL that joins multiple tables to answer a query.

**Parameters:**
```python
query: str                    # Required: The user's question
table_metadata_json: str      # Required: JSON with table schemas, relationships
```

**Table Metadata JSON Format:**
```json
[
  {
    "table_name": "catalog.schema.table",
    "columns": [
      {"name": "col1", "type": "INT", "description": "..."},
      {"name": "col2", "type": "STRING", "description": "..."}
    ],
    "relationships": [
      {"join_table": "other_table", "join_key": "patient_id"}
    ],
    "sample_data": "..."
  }
]
```

**Returns:** SQL query string

**Example Usage:**
```python
import json

metadata = [
    {
        "table_name": "yyang.hv_claims_sample.enrollment",
        "columns": [{"name": "patient_id", "type": "STRING"}, ...],
        "relationships": [{"join_table": "medical_claim", "join_key": "patient_id"}]
    },
    {
        "table_name": "yyang.hv_claims_sample.medical_claim",
        "columns": [{"name": "claim_id", "type": "STRING"}, ...]
    }
]

tool.invoke({
    "query": "Count patients with medical claims",
    "table_metadata_json": json.dumps(metadata)
})
```

---

### 3. synthesize_sql_slow_route

**Full Name:** `yyang.multi_agent_genie.synthesize_sql_slow_route`

**Purpose:** Combine SQL queries from multiple Genie agents into a unified query.

**Parameters:**
```python
query: str                    # Required: Original user question
sub_queries_json: str        # Required: JSON with sub-queries and their SQL
```

**Sub-queries JSON Format:**
```json
[
  {
    "sub_query": "Get all Medicare patients",
    "sql": "SELECT patient_id FROM enrollment WHERE pay_type = 'Medicare'",
    "space_id": "01f0956a54af123e9cd23907e8167df9"
  },
  {
    "sub_query": "Get patient claims",
    "sql": "SELECT patient_id, COUNT(*) FROM medical_claim GROUP BY patient_id",
    "space_id": "01f0956a387714969edde65458dcc22a"
  }
]
```

**Returns:** Combined SQL query string

---

### 4. execute_sql_query

**Full Name:** `yyang.multi_agent_genie.execute_sql_query`

**Purpose:** Execute a SQL query and return formatted results or error details.

**Parameters:**
```python
sql: str                      # Required: SQL query to execute
```

**Returns:** JSON string with structure:
```json
// Success case:
{
  "success": true,
  "result": "| col1 | col2 |\n|------|------|\n| val1 | val2 |",
  "row_count": 10,
  "columns": ["col1", "col2"]
}

// Error case:
{
  "success": false,
  "error": "Error message",
  "sql": "The SQL that failed"
}
```

**Example Usage:**
```python
result_json = tool.invoke({
    "sql": "SELECT COUNT(*) as total FROM yyang.hv_claims_sample.enrollment"
})

import json
result = json.loads(result_json)

if result["success"]:
    print(result["result"])  # Markdown table
else:
    print(f"Error: {result['error']}")
```

---

### 5. get_table_metadata

**Full Name:** `yyang.multi_agent_genie.get_table_metadata`

**Purpose:** Retrieve table schemas and relationships for given Genie space IDs.

**Parameters:**
```python
space_ids_json: str          # Required: JSON array of space IDs
```

**Space IDs JSON Format:**
```json
[
  "01f0956a54af123e9cd23907e8167df9",
  "01f0956a387714969edde65458dcc22a"
]
```

**Returns:** JSON string with table metadata:
```json
[
  {
    "space_id": "01f0956a54af123e9cd23907e8167df9",
    "space_title": "Provider Enrollment",
    "chunk_type": "table_schema",
    "content": "Table schema details...",
    "metadata": {...}
  },
  ...
]
```

**Example Usage:**
```python
import json

space_ids = [
    "01f0956a54af123e9cd23907e8167df9",
    "01f0956a387714969edde65458dcc22a"
]

metadata_json = tool.invoke({
    "space_ids_json": json.dumps(space_ids)
})

metadata = json.loads(metadata_json)
```

---

### 6. verbal_merge_results

**Full Name:** `yyang.multi_agent_genie.verbal_merge_results`

**Purpose:** Use LLM to merge narrative answers from multiple Genie agents into a cohesive response.

**Parameters:**
```python
query: str                    # Required: Original user question
results_json: str            # Required: JSON with results from different agents
```

**Results JSON Format:**
```json
[
  {
    "agent": "Provider Enrollment",
    "space_id": "01f0956a54af123e9cd23907e8167df9",
    "response": "There are 1,234 Medicare patients enrolled...",
    "success": true
  },
  {
    "agent": "Claims",
    "space_id": "01f0956a387714969edde65458dcc22a",
    "response": "Those patients had 5,678 medical claims...",
    "success": true
  }
]
```

**Returns:** Merged narrative response (string)

**Example Usage:**
```python
import json

results = [
    {
        "agent": "Provider Enrollment",
        "response": "There are 1,234 Medicare patients enrolled.",
        "success": True
    },
    {
        "agent": "Claims", 
        "response": "Those patients had 5,678 claims.",
        "success": True
    }
]

merged = tool.invoke({
    "query": "How many Medicare patients have claims?",
    "results_json": json.dumps(results)
})

print(merged)
# Output: "Based on the enrollment data, there are 1,234 Medicare patients.
#          Claims analysis shows these patients generated 5,678 medical claims..."
```

---

## Function Workflow Examples

### Example 1: Simple Single-Space Query

```python
# User: "How many patients are enrolled?"

# Step 1: Analyze query
plan = analyze_query_plan("How many patients are enrolled?")
# Result: { "requires_multiple_spaces": false, "relevant_space_ids": ["01f0956a54af..."] }

# Step 2: Route to Genie agent (handled by supervisor)
# Genie agent queries enrollment space directly

# No UC functions needed for simple queries!
```

### Example 2: Multi-Space Query with Join

```python
# User: "Show Medicare patients with their claim counts"

# Step 1: Analyze query
plan = analyze_query_plan("Show Medicare patients with their claim counts")
# Result: { 
#   "requires_multiple_spaces": true,
#   "relevant_space_ids": ["01f0956a54af...", "01f0956a387..."],
#   "requires_join": true,
#   "join_strategy": "fast_route"
# }

# Step 2: Get table metadata
metadata = get_table_metadata(["01f0956a54af...", "01f0956a387..."])

# Step 3: Synthesize SQL
sql = synthesize_sql_fast_route(
    "Show Medicare patients with their claim counts",
    metadata
)

# Step 4: Execute SQL
result = execute_sql_query(sql)

# Step 5: Return formatted result
```

### Example 3: Multi-Space Query without Join

```python
# User: "Compare enrollment trends and claim patterns"

# Step 1: Analyze query
plan = analyze_query_plan("Compare enrollment trends and claim patterns")
# Result: {
#   "requires_multiple_spaces": true,
#   "requires_join": false,  # No join needed!
#   "relevant_space_ids": ["01f0956a54af...", "01f0956a387..."]
# }

# Step 2: Query each Genie space (handled by supervisor)
# enrollment_result = genie_1.query("enrollment trends")
# claims_result = genie_2.query("claim patterns")

# Step 3: Verbally merge results
merged = verbal_merge_results(
    "Compare enrollment trends and claim patterns",
    [enrollment_result, claims_result]
)

# Step 4: Return merged narrative
```

---

## Performance Tips

1. **Caching:** Functions with deterministic outputs (like `get_table_metadata`) benefit from caching
2. **Batch Operations:** When possible, batch space IDs in `get_table_metadata` calls
3. **Error Handling:** Always check `success` field in `execute_sql_query` results
4. **JSON Validation:** Validate JSON inputs before passing to functions to avoid errors

---

## Error Handling

All functions return structured outputs with error information:

```python
# For functions returning JSON
result = json.loads(function_output)

if "error" in result:
    print(f"Function error: {result['error']}")
elif "success" in result and not result["success"]:
    print(f"Execution failed: {result.get('error', 'Unknown error')}")
else:
    # Process successful result
    pass
```

---

## See Also

- [UC Functions Deployment Guide](./UC_FUNCTIONS_DEPLOYMENT_GUIDE.md)
- [agent_uc_functions.py](./Notebooks/agent_uc_functions.py) - Function implementations
- [agent_autonomize.py](./Notebooks/agent_autonomize.py) - LangGraph integration

