# Unity Catalog Functions Deployment Guide

This guide explains how to deploy the UC function-based multi-agent system (`agent_autonomize.py`).

## Overview

The system uses **Unity Catalog Functions** to expose custom agent logic as callable tools within the LangGraph supervisor. This provides:
- ✅ Full LangGraph integration
- ✅ MLflow automatic tracing
- ✅ Proper tool-calling semantics
- ✅ Production-ready governance

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│         LangGraph Supervisor (create_supervisor)        │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │QueryPlanning │  │  Genie Agents │  │ ResultsMerger│ │
│  │    Agent     │  │  (3 domains)  │  │    Agent     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                 │                  │          │
│         └─────────────────┴──────────────────┘          │
│                           │                             │
│                    ┌──────▼───────┐                     │
│                    │   SQLAgent   │                     │
│                    └──────┬───────┘                     │
└───────────────────────────┼─────────────────────────────┘
                            │
                ┌───────────▼────────────┐
                │  Unity Catalog Functions │
                │                          │
                │ • analyze_query_plan     │
                │ • synthesize_sql_*       │
                │ • execute_sql_query      │
                │ • get_table_metadata     │
                │ • verbal_merge_results   │
                └──────────────────────────┘
```

## Deployment Steps

### Step 1: Upload UC Functions File

Upload `agent_uc_functions.py` to your Databricks workspace:

```bash
# Option A: Using Databricks CLI
databricks workspace import \
  Notebooks/agent_uc_functions.py \
  /Workspace/Users/<your-email>/agent_uc_functions.py \
  --language PYTHON

# Option B: Manual upload via Workspace UI
# 1. Navigate to Workspace in Databricks UI
# 2. Create/navigate to your user folder
# 3. Click "Create" → "File" → "Upload Python File"
# 4. Upload agent_uc_functions.py
```

### Step 2: Register UC Functions

#### Option A: Using the Registration Script (Recommended)

```python
# In a Databricks notebook, run:
%run /Workspace/Users/<your-email>/register_uc_functions

# When prompted, choose option 1 (SDK-based registration)
# Confirm the registration
```

#### Option B: Manual SQL Registration

If the SDK-based approach doesn't work, use SQL:

```sql
-- 1. Analyze Query Plan Function
CREATE OR REPLACE FUNCTION yyang.multi_agent_genie.analyze_query_plan(
  query STRING COMMENT 'The user question to analyze',
  vector_search_index STRING DEFAULT 'yyang.multi_agent_genie.enriched_genie_docs_chunks_vs_index' 
    COMMENT 'Vector search index name',
  num_results INT DEFAULT 5 COMMENT 'Number of relevant spaces to retrieve'
)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'Analyze a user query and create an execution plan'
AS $$
from agent_uc_functions import analyze_query_plan
return analyze_query_plan(query, vector_search_index, num_results)
$$;

-- 2. Synthesize SQL (Fast Route) Function
CREATE OR REPLACE FUNCTION yyang.multi_agent_genie.synthesize_sql_fast_route(
  query STRING COMMENT 'The user question',
  table_metadata_json STRING COMMENT 'JSON string with table metadata'
)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'Synthesize SQL query directly across multiple tables'
AS $$
from agent_uc_functions import synthesize_sql_fast_route
return synthesize_sql_fast_route(query, table_metadata_json)
$$;

-- 3. Synthesize SQL (Slow Route) Function
CREATE OR REPLACE FUNCTION yyang.multi_agent_genie.synthesize_sql_slow_route(
  query STRING COMMENT 'The original user question',
  sub_queries_json STRING COMMENT 'JSON with sub-queries and their SQL'
)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'Combine SQL from multiple Genie agents'
AS $$
from agent_uc_functions import synthesize_sql_slow_route
return synthesize_sql_slow_route(query, sub_queries_json)
$$;

-- 4. Execute SQL Function
CREATE OR REPLACE FUNCTION yyang.multi_agent_genie.execute_sql_query(
  sql STRING COMMENT 'SQL query to execute'
)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'Execute SQL and return formatted results'
AS $$
from agent_uc_functions import execute_sql_query
return execute_sql_query(sql)
$$;

-- 5. Get Table Metadata Function
CREATE OR REPLACE FUNCTION yyang.multi_agent_genie.get_table_metadata(
  space_ids_json STRING COMMENT 'JSON with list of space_ids'
)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'Retrieve table metadata for Genie spaces'
AS $$
from agent_uc_functions import get_table_metadata
return get_table_metadata(space_ids_json)
$$;

-- 6. Verbal Merge Results Function
CREATE OR REPLACE FUNCTION yyang.multi_agent_genie.verbal_merge_results(
  query STRING COMMENT 'Original user question',
  results_json STRING COMMENT 'JSON with results from different agents'
)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'Verbally merge results from multiple agents'
AS $$
from agent_uc_functions import verbal_merge_results
return verbal_merge_results(query, results_json)
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION yyang.multi_agent_genie.analyze_query_plan TO `account users`;
GRANT EXECUTE ON FUNCTION yyang.multi_agent_genie.synthesize_sql_fast_route TO `account users`;
GRANT EXECUTE ON FUNCTION yyang.multi_agent_genie.synthesize_sql_slow_route TO `account users`;
GRANT EXECUTE ON FUNCTION yyang.multi_agent_genie.execute_sql_query TO `account users`;
GRANT EXECUTE ON FUNCTION yyang.multi_agent_genie.get_table_metadata TO `account users`;
GRANT EXECUTE ON FUNCTION yyang.multi_agent_genie.verbal_merge_results TO `account users`;
```

### Step 3: Verify Function Registration

```sql
-- List all registered functions
SHOW FUNCTIONS IN yyang.multi_agent_genie;

-- Test a function
SELECT yyang.multi_agent_genie.analyze_query_plan(
  'How many patients are enrolled in Medicare?',
  'yyang.multi_agent_genie.enriched_genie_docs_chunks_vs_index',
  5
);
```

### Step 4: Deploy the Agent to Model Serving

#### In a Databricks Notebook:

```python
import mlflow
from agent_autonomize import AGENT, llm, GENIE_SPACES, UC_FUNCTION_CATALOG, UC_FUNCTION_SCHEMA

# Set MLflow experiment
mlflow.set_experiment("/Users/<your-email>/multi_agent_uc_functions")

# Log the agent
with mlflow.start_run(run_name="uc_functions_agent"):
    # Log agent configuration as parameters
    mlflow.log_param("llm_endpoint", "databricks-claude-sonnet-4-5")
    mlflow.log_param("uc_catalog", UC_FUNCTION_CATALOG)
    mlflow.log_param("uc_schema", UC_FUNCTION_SCHEMA)
    mlflow.log_param("num_genie_spaces", len(GENIE_SPACES))
    
    # Log the agent
    model_info = mlflow.langchain.log_model(
        lc_model=AGENT,
        artifact_path="agent",
        input_example={
            "messages": [
                {"role": "user", "content": "How many patients are enrolled in Medicare?"}
            ]
        },
    )
    
    print(f"Model logged to: {model_info.model_uri}")
```

#### Register and Deploy:

```python
# Register the model
model_name = "multi_agent_uc_functions"
model_version = mlflow.register_model(
    model_uri=model_info.model_uri,
    name=model_name
)

# Deploy to Model Serving
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ServedEntityInput, EndpointCoreConfigInput

w = WorkspaceClient()

endpoint_name = "multi-agent-uc-functions"

w.serving_endpoints.create(
    name=endpoint_name,
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                entity_name=model_name,
                entity_version=model_version.version,
                scale_to_zero_enabled=True,
                workload_size="Small"
            )
        ]
    )
)

print(f"✅ Endpoint created: {endpoint_name}")
```

## Configuration

### Environment Variables

You can customize the deployment using environment variables:

```python
# In your notebook or job
import os

# LLM Configuration
os.environ["LLM_ENDPOINT"] = "databricks-claude-sonnet-4-5"

# UC Function Location
os.environ["UC_FUNCTION_CATALOG"] = "yyang"
os.environ["UC_FUNCTION_SCHEMA"] = "multi_agent_genie"
```

### Genie Spaces

Update `GENIE_SPACES` in `agent_autonomize.py` to match your Genie spaces:

```python
GENIE_SPACES = [
    Genie(
        space_id="<your-space-id>",
        name="<Display Name>",
        description="<Detailed description of what this space contains>",
    ),
    # Add more spaces...
]
```

## Testing

### Test UC Functions Directly

```python
from databricks_langchain import UCFunctionToolkit

# Test query planning function
toolkit = UCFunctionToolkit(
    function_names=["yyang.multi_agent_genie.analyze_query_plan"]
)

# Get the tool
analyze_tool = toolkit.tools[0]

# Call it
result = analyze_tool.invoke({
    "query": "How many Medicare patients are there?",
    "vector_search_index": "yyang.multi_agent_genie.enriched_genie_docs_chunks_vs_index",
    "num_results": 5
})

print(result)
```

### Test the Full Agent Locally

```python
from agent_autonomize import supervisor
from langchain_core.messages import HumanMessage

# Test query
result = supervisor.invoke({
    "messages": [HumanMessage(content="How many patients are enrolled in Medicare?")]
})

# Print final response
print(result["messages"][-1].content)
```

### Test via Model Serving Endpoint

```python
from databricks_langchain import ChatDatabricks

# Connect to the endpoint
agent = ChatDatabricks(
    endpoint=endpoint_name,
    use_responses_api=True
)

# Test query
response = agent.invoke([
    {"role": "user", "content": "How many patients are enrolled in Medicare?"}
])

print(response.content)
```

## Monitoring

### MLflow Traces

All UC function calls are automatically traced in MLflow:

```python
# View traces in MLflow UI
# Navigate to: Experiments → Your Experiment → Traces tab

# Or query programmatically
import mlflow

client = mlflow.tracking.MlflowClient()
traces = client.search_traces(
    experiment_ids=["<your-experiment-id>"],
    filter_string="attributes.agent_name='QueryPlanning'"
)

for trace in traces:
    print(f"Trace ID: {trace.info.request_id}")
    print(f"Duration: {trace.info.execution_time_ms}ms")
```

### Function Performance

```sql
-- Query function execution history (if enabled)
SELECT 
  function_name,
  COUNT(*) as call_count,
  AVG(execution_time_ms) as avg_time_ms,
  MAX(execution_time_ms) as max_time_ms
FROM system.access.function_history
WHERE catalog_name = 'yyang'
  AND schema_name = 'multi_agent_genie'
  AND event_date >= current_date() - 7
GROUP BY function_name
ORDER BY call_count DESC;
```

## Troubleshooting

### Issue: "Function not found"

**Solution:**
1. Verify function exists: `SHOW FUNCTIONS IN yyang.multi_agent_genie;`
2. Check permissions: `SHOW GRANTS ON FUNCTION yyang.multi_agent_genie.analyze_query_plan;`
3. Grant execute permission if needed

### Issue: "Module 'agent_uc_functions' not found"

**Solution:**
1. Ensure `agent_uc_functions.py` is uploaded to the correct workspace location
2. Update the `PYTHON_FILE_PATH` in `register_uc_functions.py`
3. Re-register functions with correct path

### Issue: UC Function execution errors

**Solution:**
1. Test function directly in SQL notebook
2. Check function logs: `SELECT * FROM system.access.function_history WHERE function_name = '<function_name>' ORDER BY event_time DESC LIMIT 10;`
3. Verify dependencies (databricks-langchain, vector search client) are available

### Issue: LangGraph supervisor not calling functions

**Solution:**
1. Verify UCFunctionToolkit initialization: Check that function names are correct
2. Check supervisor prompt: Ensure it references the correct agent names
3. Enable verbose logging: Add `langchain.debug = True` for detailed trace

## Cost Optimization

### 1. Function Caching
UC functions support result caching for deterministic operations:

```sql
ALTER FUNCTION yyang.multi_agent_genie.get_table_metadata
SET TBLPROPERTIES ('cache_enabled' = 'true');
```

### 2. Endpoint Scaling
Enable scale-to-zero for the model serving endpoint to minimize costs:

```python
scale_to_zero_enabled=True,
workload_size="Small"  # Start with Small, scale up if needed
```

### 3. LLM Optimization
- Use cheaper models for planning/routing: `databricks-llama-3-70b-instruct`
- Reserve expensive models for final synthesis

## Next Steps

1. ✅ Register UC functions (Step 2)
2. ✅ Test functions individually (Testing section)
3. ✅ Deploy agent to Model Serving (Step 4)
4. ✅ Monitor performance (Monitoring section)
5. 🔄 Iterate on agent prompts and function implementations
6. 📊 Collect user feedback and optimize

## Additional Resources

- [Unity Catalog Functions Documentation](https://docs.databricks.com/en/sql/language-manual/sql-ref-functions-udf.html)
- [LangGraph Supervisor Pattern](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/supervisor/)
- [MLflow Agent Deployment](https://mlflow.org/docs/latest/llms/langchain/index.html)
- [Databricks Model Serving](https://docs.databricks.com/en/machine-learning/model-serving/index.html)

