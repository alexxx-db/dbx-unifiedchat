# Super Agent Multi-Agent System - Usage Guide

## Overview
This guide explains how to use the complete multi-agent system in `Super_Agent_langgraph_multiagent_genie.py`, which includes all agents from `test_uc_functions.py` integrated into the LangGraph framework from `langgraph-multiagent-genie.py`.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      SUPER AGENT                                 │
│                   (LangGraph Supervisor)                         │
│  - Orchestrates all sub-agents                                  │
│  - Manages state and handoffs                                   │
│  - Returns final result to user                                 │
└──────────┬──────────────────────────────────────────────────────┘
           ↓
┌─────────────────────┐
│ 1. CLARIFICATION    │ ← Validates query clarity
│    AGENT            │   Requests clarification if needed
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ 2. PLANNING         │ ← Analyzes query
│    AGENT            │   Searches vector index
│                     │   Identifies relevant spaces
│                     │   Creates execution plan
│                     │   Determines fast vs genie route
└──────────┬──────────┘
           ↓
     ┌─────┴─────┐
     ↓           ↓
┌────────────┐  ┌────────────────┐
│ 3a. FAST   │  │ 3b. SLOW       │
│ ROUTE      │  │ ROUTE          │
│ (UC Tools) │  │ (Genie Agents) │
└─────┬──────┘  └──────┬─────────┘
      │                │
      └────────┬───────┘
               ↓
┌─────────────────────┐
│ 4. SQL EXECUTION    │ ← Executes SQL on delta tables
│    TOOL             │   Returns results
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│    Final Answer     │
└─────────────────────┘
```

## Available Agents

### 1. Clarification Agent
**Name**: `clarification_agent`  
**Purpose**: Validates query clarity  
**Input**: User query  
**Output**: JSON with `question_clear` flag and optional clarification options

**Example**:
```python
input_data = {"input": [{"role": "user", "content": "How many patients are?"}]}
response = AGENT.predict(input_data)
# Returns: {"question_clear": false, "clarification_needed": "...", "clarification_options": [...]}
```

### 2. Planning Agent
**Name**: `planning_agent`  
**Purpose**: Creates execution plans  
**Input**: Clear user query  
**Output**: JSON with execution plan including:
- `relevant_space_ids`: Which Genie spaces to query
- `requires_join`: Whether JOIN is needed
- `join_strategy`: "table_route" or "genie_route"
- `genie_route_plan`: Mapping of space_id to partial questions

**Example**:
```python
input_data = {"input": [{"role": "user", "content": "What is the average cost of medical claims?"}]}
response = AGENT.predict(input_data)
# Returns execution plan with join strategy
```

### 3. SQL Synthesis Table Route
**Name**: `sql_synthesis_table_route`  
**Purpose**: Generates SQL using UC metadata functions  
**Tools**: 
- `get_space_summary`
- `get_table_overview`
- `get_column_detail`
- `get_space_details`

**When to Use**: 
- Complex joins across multiple tables
- Need precise control over SQL generation
- Have clear table/column requirements

**Example**:
```python
# Supervisor routes automatically based on planning agent's decision
input_data = {"input": [{"role": "user", "content": "Average cost by payer type?"}]}
response = AGENT.predict(input_data)
```

### 4. SQL Synthesis Genie Route
**Name**: `genie_route_agent` (not in supervisor by default)  
**Purpose**: Routes queries to individual Genie agents, combines their SQL  
**Tools**: All Genie agent tools (one per Genie space)

**When to Use**:
- Complex analytical questions per space
- Need Genie's domain understanding
- Queries that fit well within single space boundaries

**Example**:
```python
from agent import genie_route_agent

plan = {
    "genie_route_plan": {
        "space_id_1": "What are medical claims with diabetes?",
        "space_id_2": "What are patient demographics?"
    }
}

agent_message = {
    "messages": [{"role": "user", "content": f"Generate SQL: {json.dumps(plan)}"}]
}

result = genie_route_agent.invoke(agent_message)
```

### 5. SQL Execution Tool
**Name**: `execute_sql_tool`  
**Purpose**: Executes SQL queries on delta tables

**Example**:
```python
from agent import execute_sql_on_delta_tables

sql = "SELECT COUNT(*) FROM yyang.multi_agent_genie.medical_claim"
result = execute_sql_on_delta_tables(sql, max_rows=100, return_format="dict")

print(result["success"])  # True/False
print(result["result"])   # Query results
print(result["row_count"])  # Number of rows
```

## Quick Start

### 1. Basic Usage
```python
from agent import AGENT

# Simple query
input_example = {
    "input": [
        {"role": "user", "content": "How many patients are in the dataset?"}
    ]
}

response = AGENT.predict(input_example)
print(response)
```

### 2. Streaming Response
```python
for event in AGENT.predict_stream(input_example):
    print(event.model_dump(exclude_none=True))
```

### 3. Multi-Turn Conversation
```python
input_conversation = {
    "input": [
        {"role": "user", "content": "What tables are available?"},
        {"role": "assistant", "content": "We have medical_claim, diagnosis, enrollment tables."},
        {"role": "user", "content": "Show me average costs from medical_claim"}
    ]
}

response = AGENT.predict(input_conversation)
```

## Advanced Usage

### Using Genie Route Agent Directly
```python
from agent import genie_route_agent, genie_agent_tools

# Create plan (normally from planning agent)
plan = {
    "original_query": "Complex multi-space query",
    "join_strategy": "genie_route",
    "genie_route_plan": {
        "01f0956a387714969edde65458dcc22a": "Partial question 1",
        "01f0956a54af123e9cd23907e8167df9": "Partial question 2"
    }
}

# Invoke genie route agent
agent_message = {
    "messages": [
        {"role": "user", "content": f"Generate SQL: {json.dumps(plan, indent=2)}"}
    ]
}

result = genie_route_agent.invoke(agent_message)
final_sql = result["messages"][-1].content
```

### End-to-End Workflow with Execution
```python
from agent import AGENT, execute_sql_on_delta_tables
import json

# Step 1: Get SQL from supervisor
query = "What is the average cost of medical claims in 2024?"
input_data = {"input": [{"role": "user", "content": query}]}
response = AGENT.predict(input_data)

# Step 2: Extract SQL from response
# Parse response to get the SQL query
# (Actual parsing depends on response format)

# Step 3: Execute SQL
result = execute_sql_on_delta_tables(
    sql_query=extracted_sql,
    max_rows=100,
    return_format="dict"
)

if result["success"]:
    print("Results:", result["result"])
else:
    print("Error:", result["error"])
```

### Comparing Fast vs Genie Route
```python
test_query = "Average medical claim cost by payer type?"

# Table Route
fast_input = {
    "input": [
        {"role": "user", "content": f"{test_query} Use table_route."}
    ]
}
fast_result = AGENT.predict(fast_input)

# Genie Route (requires planning agent output first)
slow_input = {
    "input": [
        {"role": "user", "content": f"{test_query} Use genie_route."}
    ]
}
slow_result = AGENT.predict(slow_input)

# Compare results
print("Table Route SQL:", fast_result)
print("Genie Route SQL:", slow_result)
```

## Configuration

### Required Settings in agent.py
```python
# Update these values
CATALOG = "your_catalog"
SCHEMA = "your_schema"
TABLE_NAME = f"{CATALOG}.{SCHEMA}.enriched_genie_docs_chunks"
VECTOR_SEARCH_INDEX = f"{CATALOG}.{SCHEMA}.enriched_genie_docs_chunks_vs_index"
LLM_ENDPOINT_NAME = "databricks-claude-sonnet-4-5"
```

### Prerequisites
1. ✅ Unity Catalog functions registered:
   - `get_space_summary`
   - `get_table_overview`
   - `get_column_detail`
   - `get_space_details`

2. ✅ Genie Spaces created and configured

3. ✅ Vector search index created for space summaries

4. ✅ Delta tables with enriched metadata

## Extending the Supervisor

### Add SQL Execution Agent
```python
# In agent.py, add to IN_CODE_AGENTS:
IN_CODE_AGENTS.append(
    InCodeSubAgent(
        tools=[],  # Could add execute_sql_tool if registered as UC function
        name="sql_execution_agent",
        description="Executes SQL queries on delta tables and returns results.",
        system_prompt="""
        You are a SQL execution agent.
        Execute the provided SQL query and return formatted results.
        Handle errors gracefully and provide clear error messages.
        """
    )
)
```

### Add Genie Route to Supervisor
```python
# Option 1: Modify create_langgraph_supervisor
def create_langgraph_supervisor(
    llm: Runnable,
    in_code_agents: list[InCodeSubAgent] = [],
    additional_agents: list[Runnable] = [],  # New parameter
):
    agents = []
    
    # Process in_code_agents...
    
    # Add pre-built agents
    agents.extend(additional_agents)
    
    # Create supervisor...

# Then call with:
supervisor = create_langgraph_supervisor(
    llm,
    IN_CODE_AGENTS,
    additional_agents=[genie_route_agent]
)
```

## Testing

### Run All Tests
```bash
# In Databricks notebook, run all cells in order:
# 1. Install dependencies
# 2. Restart Python
# 3. Test basic agent
# 4. Test genie route
# 5. Test SQL execution
# 6. Test end-to-end workflow
```

### MLflow Tracing
```python
import mlflow
mlflow.langchain.autolog()

# All agent calls are automatically traced
response = AGENT.predict(input_data)

# View traces in MLflow UI
```

## Common Patterns

### Pattern 1: Clarification → Planning → Table Route → Execution
```python
query = "Average medical claim cost?"
input_data = {"input": [{"role": "user", "content": query}]}

# Supervisor handles routing automatically
response = AGENT.predict(input_data)

# Extract and execute SQL
sql = extract_sql_from_response(response)
result = execute_sql_on_delta_tables(sql)
```

### Pattern 2: Complex Multi-Space Query with Genie Route
```python
query = "Average cost of medical claims for diabetic patients by age group?"
input_data = {
    "input": [
        {"role": "user", "content": f"{query} Use genie_route if needed."}
    ]
}

# Planning agent determines genie route is needed
response = AGENT.predict(input_data)

# Supervisor routes to genie_route_agent (if integrated)
# Or manually call genie_route_agent with plan
```

### Pattern 3: Iterative Refinement
```python
conversation = []

# Initial query
conversation.append({"role": "user", "content": "Show me medical claims"})
response1 = AGENT.predict({"input": conversation})
conversation.append({"role": "assistant", "content": str(response1)})

# Refine
conversation.append({"role": "user", "content": "Filter for 2024 only"})
response2 = AGENT.predict({"input": conversation})
conversation.append({"role": "assistant", "content": str(response2)})

# Further refine
conversation.append({"role": "user", "content": "Group by payer type"})
response3 = AGENT.predict({"input": conversation})
```

## Troubleshooting

### Issue: Agent not routing to correct sub-agent
**Solution**: Check planning agent output for `join_strategy` field. Update agent descriptions to be more specific.

### Issue: Genie Route agent not finding Genie tools
**Solution**: Verify `genie_agent_tools` is populated. Check tool descriptions include space_id.

### Issue: SQL execution fails
**Solution**: 
- Check SQL syntax
- Verify table names are correct
- Check user permissions
- Use `execute_sql_on_delta_tables` with `return_format="dict"` for detailed error messages

### Issue: UC functions not found
**Solution**: 
- Verify functions are registered: `spark.sql("SHOW FUNCTIONS IN catalog.schema")`
- Check function names match in `UC_FUNCTION_NAMES`
- Verify permissions

## Best Practices

1. **Clear Queries**: Provide specific, well-formed questions
2. **Use Context**: Maintain conversation history for follow-up questions
3. **Monitor Traces**: Use MLflow to understand agent routing decisions
4. **Test Both Routes**: Compare fast vs genie route for your use cases
5. **Error Handling**: Always check `success` field in execution results
6. **Resource Limits**: Use `max_rows` parameter to prevent large result sets
7. **Incremental Development**: Start with simple queries, gradually increase complexity

## Performance Tips

1. **Table Route**: Generally faster for complex joins, use when you need precise SQL control
2. **Genie Route**: Better for leveraging Genie's understanding, use for analytical questions
3. **Caching**: Plan results can be cached if same query is repeated
4. **Batch Queries**: Group related questions for efficiency
5. **Limit Results**: Always use LIMIT clauses for large tables

## Next Steps

1. Run the complete notebook end-to-end
2. Test with your specific queries
3. Compare table route vs genie route accuracy
4. Integrate SQL execution into supervisor workflow
5. Deploy to production
6. Monitor and optimize based on MLflow traces

## Resources

- **Main File**: `Notebooks/Super_Agent_langgraph_multiagent_genie.py`
- **Reference**: `Notebooks/test_uc_functions.py`
- **Framework**: `Notebooks/langgraph-multiagent-genie.py`
- **Summary**: `Notebooks/SUPER_AGENT_ADDITIONS_SUMMARY.md`
- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **Databricks Agents**: https://docs.databricks.com/en/generative-ai/agent-framework/
