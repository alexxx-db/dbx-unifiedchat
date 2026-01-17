# Testing Plan for Multi-Agent System Notebooks

**Created:** December 4, 2025  
**Purpose:** Validate notebooks 04 and 05 work correctly with current Databricks configuration

---

## Overview

This document outlines a systematic testing plan for the two key notebooks:
1. **04_VS_Enriched_Genie_Spaces.py** - Vector Search Index Creation
2. **05_Multi_Agent_System.py** - Multi-Agent System Deployment

---

## Pre-Test Checklist

### ✅ Prerequisites Verification

- [ ] **Databricks Workspace Access**
  - Confirm you can access the Databricks workspace
  - Verify you have appropriate permissions (workspace admin or similar)

- [ ] **Unity Catalog Setup**
  - Catalog exists: `yyang` (or your configured catalog)
  - Schema exists: `multi_agent_genie` (or your configured schema)
  - You have CREATE permissions on the schema

- [ ] **Source Data Available**
  - Table `yyang.multi_agent_genie.enriched_genie_docs_chunks` exists
  - Table contains data from previous enrichment step (02_Table_MetaInfo_Enrichment.py)
  - Run: `SELECT COUNT(*) FROM yyang.multi_agent_genie.enriched_genie_docs_chunks`

- [ ] **Genie Spaces Accessible**
  - Verify the 5 Genie space IDs are valid:
    - `01f072dbd668159d99934dfd3b17f544` (GENIE_PATIENT)
    - `01f08f4d1f5f172ea825ec8c9a3c6064` (MEDICATIONS)
    - `01f073c5476313fe8f51966e3ce85bd7` (GENIE_DIAGNOSIS_STAGING)
    - `01f07795f6981dc4a99d62c9fc7c2caa` (GENIE_TREATMENT)
    - `01f08a9fd9ca125a986d01c1a7a5b2fe` (GENIE_LABORATORY_BIOMARKERS)

- [ ] **Model Endpoints Available**
  - LLM endpoint exists: `databricks-claude-sonnet-4-5` (or your configured endpoint)
  - Embedding endpoint exists: `databricks-gte-large-en`

---

## Test Phase 1: Notebook 04 - Vector Search Index

### Test 1.1: Environment Setup ✅

**Objective:** Verify the notebook can import required libraries and access resources

**Commands:**
```sql
-- In Databricks notebook cell
%pip install -U databricks-vectorsearch
dbutils.library.restartPython()
```

**Expected Result:**
- ✅ Package installs without errors
- ✅ Python restarts successfully

**How to Verify:**
```python
# Next cell
from databricks.vector_search.client import VectorSearchClient
print("✓ Import successful")
```

---

### Test 1.2: Source Table Verification ✅

**Objective:** Confirm enriched docs table exists and has data

**Command:**
```python
catalog_name = "yyang"
schema_name = "multi_agent_genie"
source_table = "enriched_genie_docs_chunks"
source_table_name = f"{catalog_name}.{schema_name}.{source_table}"

df_source = spark.table(source_table_name)
count = df_source.count()
print(f"✓ Source table exists with {count} records")

# Check schema
df_source.printSchema()

# Check sample data
display(df_source.limit(5))
```

**Expected Result:**
- ✅ Table exists
- ✅ Has > 0 records
- ✅ Contains required columns:
  - `chunk_id` (primary key)
  - `chunk_type` (space_summary, table_overview, column_detail)
  - `space_id`, `space_title`
  - `table_name`, `column_name`
  - `searchable_content` (text for embedding)
  - `is_categorical`, `is_temporal`, `is_identifier`, `has_value_dictionary`

**Troubleshooting:**
- If table doesn't exist → Run `02_Table_MetaInfo_Enrichment.py` first
- If no records → Check previous notebook execution

---

### Test 1.3: Vector Search Endpoint Creation ✅

**Objective:** Create or verify vector search endpoint exists

**Command:**
```python
from databricks.vector_search.client import VectorSearchClient

client = VectorSearchClient()
vs_endpoint_name = "vs_endpoint_genie_multi_agent_vs"

# List existing endpoints
endpoints = client.list_endpoints().get('endpoints', [])
endpoint_names = [ep['name'] for ep in endpoints]
print(f"Existing endpoints: {endpoint_names}")

# Create or get endpoint
if vs_endpoint_name in endpoint_names:
    print(f"✓ Endpoint '{vs_endpoint_name}' already exists")
    endpoint = client.get_endpoint(vs_endpoint_name)
else:
    print(f"Creating endpoint '{vs_endpoint_name}'...")
    endpoint = client.create_endpoint(
        name=vs_endpoint_name,
        endpoint_type="STANDARD"
    )
    print(f"✓ Created endpoint '{vs_endpoint_name}'")

# Wait for endpoint to be ready
client.wait_for_endpoint(vs_endpoint_name, "ONLINE")
print(f"✓ Endpoint is ONLINE")
```

**Expected Result:**
- ✅ Endpoint created or already exists
- ✅ Endpoint status is "ONLINE"

**Troubleshooting:**
- If creation fails → Check workspace permissions
- If stays in PROVISIONING → Wait 2-3 minutes, then check again
- If FAILED → Check error message, may need to delete and recreate

---

### Test 1.4: Vector Index Creation ✅

**Objective:** Create delta sync vector search index

**Command:**
```python
import time

index_name = f"{catalog_name}.{schema_name}.{source_table}_vs_index"
embedding_model = "databricks-gte-large-en"

print(f"Creating index: {index_name}")
print(f"  Source: {source_table_name}")
print(f"  Primary key: chunk_id")
print(f"  Embedding column: searchable_content")
print(f"  Embedding model: {embedding_model}")

# Enable Change Data Feed on source table
spark.sql(f"ALTER TABLE {source_table_name} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")

# Check if index exists, delete if so
try:
    existing_index = client.get_index(index_name=index_name)
    print(f"Deleting existing index...")
    client.delete_index(index_name=index_name)
    time.sleep(5)
except Exception:
    print(f"No existing index, creating new...")

# Create index
index = client.create_delta_sync_index(
    endpoint_name=vs_endpoint_name,
    source_table_name=source_table_name,
    index_name=index_name,
    pipeline_type="TRIGGERED",
    primary_key="chunk_id",
    embedding_source_column="searchable_content",
    embedding_model_endpoint_name=embedding_model
)

print(f"✓ Index creation initiated: {index_name}")
```

**Expected Result:**
- ✅ Change Data Feed enabled
- ✅ Index creation starts successfully
- ✅ No immediate errors

**Troubleshooting:**
- If CDC fails → Check table permissions
- If index creation fails → Check embedding endpoint availability
- If timeout → Continue to next test (index builds asynchronously)

---

### Test 1.5: Wait for Index to be Online ⏱️

**Objective:** Monitor index build progress

**Command:**
```python
print("Waiting for index to be ONLINE...")
max_wait_time = 600  # 10 minutes
start_time = time.time()

while time.time() - start_time < max_wait_time:
    try:
        index_status = index.describe()
        detailed_state = index_status.get('status', {}).get('detailed_state', '')
        
        print(f"  [{int(time.time() - start_time)}s] State: {detailed_state}")
        
        if detailed_state.startswith('ONLINE'):
            print(f"✓ Index is ONLINE!")
            break
        elif 'FAILED' in detailed_state:
            print(f"✗ Index creation failed: {detailed_state}")
            print(f"Full status: {index_status}")
            raise Exception(f"Index failed: {detailed_state}")
        
        time.sleep(10)
    except Exception as e:
        if time.time() - start_time >= max_wait_time:
            raise Exception(f"Timeout waiting for index: {str(e)}")
        time.sleep(10)

# Display final status
display(index.describe())
```

**Expected Result:**
- ✅ Index status progresses: PROVISIONING → ONLINE_INDEX_BUILD → ONLINE
- ✅ Reaches ONLINE status within 10 minutes
- ✅ No FAILED status

**Timing Expectations:**
- Small dataset (<1000 rows): 2-3 minutes
- Medium dataset (1000-10000 rows): 5-8 minutes
- Large dataset (>10000 rows): 10+ minutes

**Troubleshooting:**
- If FAILED → Check error message in status
- If timeout → May need more time, check async in Databricks UI
- If stuck in INDEX_BUILD → Check embedding endpoint availability

---

### Test 1.6: Vector Search Queries ✅

**Objective:** Test semantic search with filters

**Command:**
```python
vs_index = client.get_index(index_name=index_name)

# Test 1: General search across all chunk types
print("\n" + "="*80)
print("Test 1: General Search")
print("="*80)

results = vs_index.similarity_search(
    query_text="patient age and demographics",
    columns=["chunk_id", "chunk_type", "space_title", "table_name", "column_name", "score"],
    num_results=5
)

result_data = results.get('result', {})
data_array = result_data.get('data_array', [])
print(f"Found {len(data_array)} results")

# Display results
if len(data_array) > 0:
    manifest = result_data.get('manifest', {})
    result_df = spark.createDataFrame(data_array, schema=manifest.get('columns', []))
    display(result_df)
else:
    print("⚠ No results found")

# Test 2: Space-level search with filters
print("\n" + "="*80)
print("Test 2: Space Discovery (chunk_type filter)")
print("="*80)

results = vs_index.similarity_search(
    query_text="What data contains patient claims?",
    columns=["chunk_id", "chunk_type", "space_title", "score"],
    filters={"chunk_type": "space_summary"},
    num_results=3
)

result_data = results.get('result', {})
data_array = result_data.get('data_array', [])
print(f"Found {len(data_array)} space-level results")

if len(data_array) > 0:
    manifest = result_data.get('manifest', {})
    result_df = spark.createDataFrame(data_array, schema=manifest.get('columns', []))
    display(result_df)

# Test 3: Column-level search with metadata filters
print("\n" + "="*80)
print("Test 3: Column Discovery (categorical filter)")
print("="*80)

results = vs_index.similarity_search(
    query_text="location or facility type",
    columns=["chunk_id", "table_name", "column_name", "is_categorical", "score"],
    filters={"chunk_type": "column_detail", "has_value_dictionary": True},
    num_results=5
)

result_data = results.get('result', {})
data_array = result_data.get('data_array', [])
print(f"Found {len(data_array)} categorical column results")

if len(data_array) > 0:
    manifest = result_data.get('manifest', {})
    result_df = spark.createDataFrame(data_array, schema=manifest.get('columns', []))
    display(result_df)
```

**Expected Result:**
- ✅ All 3 test queries return results
- ✅ Results are semantically relevant to queries
- ✅ Filters work correctly (chunk_type, metadata)
- ✅ Scores are reasonable (typically > 0.5 for good matches)

**Quality Checks:**
- Results should be relevant to the query
- Space-level queries should only return `chunk_type = "space_summary"`
- Column-level queries should include column metadata
- Scores should be ranked (highest first)

**Troubleshooting:**
- If no results → Index may be empty, check source table
- If irrelevant results → May need more data or better chunking
- If filters don't work → Check filter syntax (dict format for STANDARD endpoints)

---

### Test 1.7: UC Functions Creation ✅

**Objective:** Create Unity Catalog functions for agent access

**Command:**
```python
# Function 1: General chunk search
uc_chunk_search_name = f"{catalog_name}.{schema_name}.search_genie_chunks"

spark.sql(f"DROP FUNCTION IF EXISTS {uc_chunk_search_name}")

create_sql = f"""
CREATE OR REPLACE FUNCTION {uc_chunk_search_name}(
    query STRING,
    num_results INT
)
RETURNS TABLE(
    chunk_id INT, 
    chunk_type STRING, 
    space_id STRING, 
    space_title STRING, 
    table_name STRING,
    column_name STRING,
    is_categorical BOOLEAN,
    is_temporal BOOLEAN,
    is_identifier BOOLEAN,
    has_value_dictionary BOOLEAN,
    score DOUBLE
)
LANGUAGE SQL
COMMENT 'Search for relevant chunks based on natural language query'
RETURN SELECT chunk_id, chunk_type, space_id, space_title, table_name, column_name,
              is_categorical, is_temporal, is_identifier, has_value_dictionary, score
FROM vector_search(
    index => '{index_name}',
    query => query,
    num_results => num_results
)
ORDER BY score DESC
"""

spark.sql(create_sql)
print(f"✓ Created: {uc_chunk_search_name}")

# Function 2: Space-level search
uc_space_search_name = f"{catalog_name}.{schema_name}.search_genie_spaces"

spark.sql(f"DROP FUNCTION IF EXISTS {uc_space_search_name}")

create_sql = f"""
CREATE OR REPLACE FUNCTION {uc_space_search_name}(
    query STRING,
    num_results INT
)
RETURNS TABLE(space_id STRING, space_title STRING, score DOUBLE)
LANGUAGE SQL
COMMENT 'Search for relevant Genie spaces'
RETURN SELECT space_id, space_title, score
FROM vector_search(
    index => '{index_name}',
    query => query,
    num_results => num_results,
    filters => 'chunk_type = "space_summary"'
)
ORDER BY score DESC
"""

spark.sql(create_sql)
print(f"✓ Created: {uc_space_search_name}")

# Test the functions
print("\nTesting UC Functions:")
test_result = spark.sql(f"""
    SELECT * FROM {uc_space_search_name}(
        'What spaces contain patient data?',
        3
    )
""")
display(test_result)
```

**Expected Result:**
- ✅ Functions created without errors
- ✅ Test query returns results
- ✅ Functions are accessible from SQL

**Troubleshooting:**
- If CREATE fails → Check schema permissions
- If test query fails → Check function syntax and index name
- If no results → Index may not be ready

---

### Test 1.8: Notebook 04 Summary ✅

**Verification Checklist:**

```python
# Run this summary check
print("="*80)
print("NOTEBOOK 04 - VERIFICATION SUMMARY")
print("="*80)

checks = {
    "Vector Search Endpoint": vs_endpoint_name,
    "Index Name": index_name,
    "UC Function (chunks)": uc_chunk_search_name,
    "UC Function (spaces)": uc_space_search_name,
}

for name, value in checks.items():
    print(f"✓ {name}: {value}")

# Verify index is queryable
try:
    test_query = vs_index.similarity_search(
        query_text="test",
        columns=["chunk_id"],
        num_results=1
    )
    print(f"\n✓ Index is queryable")
except Exception as e:
    print(f"\n✗ Index query failed: {str(e)}")

# Verify UC functions work
try:
    test_result = spark.sql(f"SELECT * FROM {uc_space_search_name}('patient', 1)")
    print(f"✓ UC functions work")
except Exception as e:
    print(f"✗ UC function failed: {str(e)}")

print("\n" + "="*80)
print("✅ Notebook 04 completed successfully!")
print("Next: Run Notebook 05 - Multi-Agent System")
print("="*80)
```

---

## Test Phase 2: Notebook 05 - Multi-Agent System

### Test 2.1: Dependencies Installation ✅

**Objective:** Install required packages

**Command:**
```python
%pip install -U -qqq langgraph-supervisor==0.0.30 mlflow[databricks] databricks-langchain databricks-agents databricks-vectorsearch
dbutils.library.restartPython()
```

**Expected Result:**
- ✅ All packages install successfully
- ✅ Python restarts without errors

**Version Check (after restart):**
```python
import langgraph_supervisor
import mlflow
import databricks_langchain
from databricks import agents

print(f"langgraph-supervisor: {langgraph_supervisor.__version__}")
print(f"mlflow: {mlflow.__version__}")
print(f"databricks-langchain: {databricks_langchain.__version__}")
print("✓ All imports successful")
```

---

### Test 2.2: Agent.py File Check ✅

**Objective:** Verify agent.py exists and contains correct configuration

**Command:**
```python
import os

agent_file = "agent.py"
if os.path.exists(agent_file):
    print(f"✓ {agent_file} exists")
    
    # Check file size
    with open(agent_file, 'r') as f:
        content = f.read()
        print(f"  File size: {len(content)} bytes")
        
    # Check key configurations
    if "yyang.multi_agent_genie.search_genie_spaces" in content:
        print(f"✓ Vector search function name is correct")
    else:
        print(f"⚠ Vector search function name may need updating")
        
    # Check Genie space IDs
    expected_spaces = [
        "01f072dbd668159d99934dfd3b17f544",
        "01f08f4d1f5f172ea825ec8c9a3c6064",
        "01f073c5476313fe8f51966e3ce85bd7",
        "01f07795f6981dc4a99d62c9fc7c2caa",
        "01f08a9fd9ca125a986d01c1a7a5b2fe",
    ]
    
    for space_id in expected_spaces:
        if space_id in content:
            print(f"✓ Space {space_id[:8]}... found")
        else:
            print(f"⚠ Space {space_id[:8]}... not found")
else:
    print(f"✗ {agent_file} not found!")
    print(f"  Please ensure agent.py is in the same directory as this notebook")
```

**Expected Result:**
- ✅ agent.py exists
- ✅ Contains correct vector search function name
- ✅ Contains all 5 Genie space IDs
- ✅ File size > 20,000 bytes (complete file)

---

### Test 2.3: Import Agent Module ✅

**Objective:** Verify agent module can be imported

**Command:**
```python
dbutils.library.restartPython()

# After restart
try:
    from agent import AGENT
    print("✓ Successfully imported AGENT from agent.py")
    print(f"  Agent type: {type(AGENT)}")
except Exception as e:
    print(f"✗ Failed to import agent: {str(e)}")
    import traceback
    traceback.print_exc()
```

**Expected Result:**
- ✅ Import succeeds
- ✅ AGENT is an instance of `LangGraphResponsesAgent`

**Troubleshooting:**
- If import fails → Check for syntax errors in agent.py
- If dependencies missing → Rerun pip install
- If Genie spaces error → Check space IDs are valid

---

### Test 2.4: Simple Agent Test ✅

**Objective:** Test basic agent functionality

**Command:**
```python
from agent import AGENT

# Test 1: Check available tools/agents
input_example = {
    "input": [
        {"role": "user", "content": "What tools and agents do you have access to?"}
    ]
}

print("="*80)
print("TEST: Available Agents and Tools")
print("="*80)

try:
    for event in AGENT.predict_stream(input_example):
        result = event.model_dump(exclude_none=True)
        print(result)
    print("\n✓ Agent responded successfully")
except Exception as e:
    print(f"✗ Agent failed: {str(e)}")
    import traceback
    traceback.print_exc()
```

**Expected Result:**
- ✅ Agent processes the request
- ✅ Lists available agents (ThinkingPlanning, Genie agents, SQLSynthesis, SQLExecution)
- ✅ No errors or exceptions

**Response Quality:**
- Should mention ThinkingPlanningAgent
- Should list Genie spaces (GENIE_PATIENT, MEDICATIONS, etc.)
- Should mention SQL synthesis and execution capabilities

---

### Test 2.5: Single-Space Query Test ✅

**Objective:** Test query that uses only one Genie space

**Command:**
```python
# Test: Simple single-space question
input_example = {
    "input": [
        {"role": "user", "content": "How many patients are older than 65 years?"}
    ]
}

print("\n" + "="*80)
print("TEST: Single Space Query - Patient Demographics")
print("="*80)

try:
    responses = []
    for event in AGENT.predict_stream(input_example):
        result = event.model_dump(exclude_none=True)
        print(result)
        responses.append(result)
    
    print("\n✓ Query completed")
    
    # Check if thinking agent was called
    has_thinking = any("ThinkingPlanning" in str(r) for r in responses)
    # Check if appropriate Genie was called
    has_genie = any("GENIE_PATIENT" in str(r) for r in responses)
    
    print(f"\n{'✓' if has_thinking else '✗'} ThinkingPlanning agent invoked")
    print(f"{'✓' if has_genie else '✗'} GENIE_PATIENT agent invoked")
    
except Exception as e:
    print(f"✗ Query failed: {str(e)}")
    import traceback
    traceback.print_exc()
```

**Expected Result:**
- ✅ ThinkingPlanningAgent analyzes the query
- ✅ Identifies this as single-space query
- ✅ Routes to GENIE_PATIENT agent
- ✅ Returns count or SQL query
- ✅ Does not call SQLSynthesis or SQLExecution (Genie handles it)

**Quality Checks:**
- Response should include patient count or indicate it's < 10
- SQL query should be shown (if available)
- No errors about missing spaces or agents

---

### Test 2.6: Cross-Domain Query Test ⏱️

**Objective:** Test query requiring multiple Genie spaces with join

**Command:**
```python
# Test: Cross-domain question requiring join
input_example = {
    "input": [
        {"role": "user", "content": "How many patients older than 50 years are on Voltaren?"}
    ]
}

print("\n" + "="*80)
print("TEST: Cross-Domain Query - Patients + Medications")
print("="*80)

try:
    responses = []
    for event in AGENT.predict_stream(input_example):
        result = event.model_dump(exclude_none=True)
        print(result)
        responses.append(result)
    
    print("\n✓ Query completed")
    
    # Check workflow
    has_thinking = any("ThinkingPlanning" in str(r) for r in responses)
    has_sql_synthesis = any("SQLSynthesis" in str(r) for r in responses)
    has_sql_execution = any("SQLExecution" in str(r) for r in responses)
    
    print(f"\n{'✓' if has_thinking else '✗'} ThinkingPlanning agent invoked")
    print(f"{'✓' if has_sql_synthesis else '✗'} SQLSynthesis agent invoked")
    print(f"{'✓' if has_sql_execution else '✗'} SQLExecution agent invoked")
    
except Exception as e:
    print(f"✗ Query failed: {str(e)}")
    import traceback
    traceback.print_exc()
```

**Expected Result:**
- ✅ ThinkingPlanningAgent identifies multi-space query
- ✅ Determines JOIN is needed
- ✅ Chooses table_route or genie_route
- ✅ SQLSynthesisAgent creates combined query
- ✅ SQLExecutionAgent runs query
- ✅ Returns final count

**Workflow Options:**
- **Table Route:** ThinkingPlanning → SQLSynthesis → SQLExecution
- **Genie Route:** ThinkingPlanning → GENIE_PATIENT → MEDICATIONS → SQLSynthesis → SQLExecution

**Quality Checks:**
- SQL should join patient and medication tables
- Filters for age > 50 and medication = "Voltaren"
- Result should be a count

---

### Test 2.7: Clarification Test ✅

**Objective:** Test that agent asks for clarification on unclear questions

**Command:**
```python
# Test: Unclear question
input_example = {
    "input": [
        {"role": "user", "content": "Tell me about patients with cancer"}
    ]
}

print("\n" + "="*80)
print("TEST: Unclear Question - Should Request Clarification")
print("="*80)

try:
    responses = []
    for event in AGENT.predict_stream(input_example):
        result = event.model_dump(exclude_none=True)
        print(result)
        responses.append(result)
    
    print("\n✓ Query completed")
    
    # Check if clarification was requested
    full_response = "\n".join(str(r) for r in responses)
    has_clarification = any(keyword in full_response.lower() for keyword in 
                           ["clarif", "specific", "more details", "what would you like"])
    
    print(f"\n{'✓' if has_clarification else '⚠'} Clarification requested")
    
except Exception as e:
    print(f"✗ Query failed: {str(e)}")
    import traceback
    traceback.print_exc()
```

**Expected Result:**
- ✅ ThinkingPlanningAgent identifies question as unclear
- ✅ Asks for clarification
- ✅ Provides options or examples of what user might mean
- ✅ Does not attempt to execute query

**Quality Checks:**
- Response should be helpful and guide user
- May offer options like:
  - "Do you want to know the count of cancer patients?"
  - "Do you want to see specific cancer types?"
  - "Do you want to know about treatments for cancer patients?"

---

### Test 2.8: Performance Metrics ⏱️

**Objective:** Measure agent performance across test suite

**Command:**
```python
import pandas as pd
from datetime import datetime

test_suite = [
    {
        "query": "How many patients are older than 50?",
        "category": "simple",
        "expected_agents": ["ThinkingPlanning", "GENIE_PATIENT"]
    },
    {
        "query": "How many patients older than 50 are on Voltaren?",
        "category": "complex",
        "expected_agents": ["ThinkingPlanning", "SQLSynthesis", "SQLExecution"]
    },
    {
        "query": "What are common diagnoses and common medications?",
        "category": "medium",
        "expected_agents": ["ThinkingPlanning", "GENIE_DIAGNOSIS", "MEDICATIONS"]
    },
]

results = []

for test_case in test_suite:
    print(f"\n{'='*80}")
    print(f"Testing: {test_case['query']}")
    print(f"{'='*80}")
    
    start_time = datetime.now()
    
    try:
        input_example = {
            "input": [{"role": "user", "content": test_case["query"]}]
        }
        
        response = AGENT.predict(input_example)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        results.append({
            "query": test_case["query"],
            "category": test_case["category"],
            "duration_seconds": duration,
            "success": True,
            "response_length": len(str(response)),
        })
        
        print(f"✓ Success ({duration:.2f}s)")
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        results.append({
            "query": test_case["query"],
            "category": test_case["category"],
            "duration_seconds": duration,
            "success": False,
            "error": str(e),
        })
        
        print(f"✗ Failed: {str(e)}")

# Display results
df_results = pd.DataFrame(results)
display(df_results)

# Summary statistics
print("\n" + "="*80)
print("PERFORMANCE SUMMARY")
print("="*80)
print(f"Total tests: {len(results)}")
print(f"Success rate: {df_results['success'].mean() * 100:.1f}%")
print(f"Average duration: {df_results['duration_seconds'].mean():.2f}s")
print(f"Min duration: {df_results['duration_seconds'].min():.2f}s")
print(f"Max duration: {df_results['duration_seconds'].max():.2f}s")
```

**Expected Result:**
- ✅ Success rate ≥ 66% (2/3 tests pass)
- ✅ Average duration < 30 seconds
- ✅ No timeout errors

**Performance Targets:**
- Simple queries: < 10 seconds
- Medium queries: < 20 seconds
- Complex queries: < 40 seconds

---

### Test 2.9: MLflow Logging Test ✅

**Objective:** Verify agent can be logged to MLflow

**Command:**
```python
import mlflow
from mlflow.models import infer_signature

# Set experiment
mlflow.set_experiment("/Users/" + spark.sql("SELECT current_user()").collect()[0][0] + "/multi_agent_genie_test")

# Test input/output for signature
test_input = {
    "input": [
        {"role": "user", "content": "How many patients are older than 50?"}
    ]
}

print("Testing MLflow logging...")

try:
    # Get test output
    test_output = AGENT.predict(test_input)
    
    # Infer signature
    signature = infer_signature(test_input, test_output)
    print(f"✓ Signature inferred successfully")
    
    # Start MLflow run
    with mlflow.start_run(run_name="test_agent_logging") as run:
        # Log the model
        mlflow.pyfunc.log_model(
            artifact_path="agent",
            python_model=AGENT,
            signature=signature,
            input_example=test_input,
            pip_requirements=[
                "langgraph-supervisor==0.0.30",
                "mlflow[databricks]",
                "databricks-langchain",
                "databricks-agents",
                "databricks-vectorsearch",
            ],
            code_paths=["agent.py"],
        )
        
        run_id = run.info.run_id
        model_uri = f"runs:/{run_id}/agent"
        
        print(f"✓ Model logged successfully!")
        print(f"  Run ID: {run_id}")
        print(f"  Model URI: {model_uri}")
        
except Exception as e:
    print(f"✗ MLflow logging failed: {str(e)}")
    import traceback
    traceback.print_exc()
```

**Expected Result:**
- ✅ Signature inferred correctly
- ✅ Model logged to MLflow
- ✅ Run ID and Model URI returned
- ✅ Code paths (agent.py) included

**Troubleshooting:**
- If signature inference fails → Check test input/output format
- If logging fails → Check MLflow experiment permissions
- If code_paths error → Ensure agent.py is in current directory

---

### Test 2.10: Notebook 05 Summary ✅

**Verification Checklist:**

```python
print("="*80)
print("NOTEBOOK 05 - VERIFICATION SUMMARY")
print("="*80)

checks = [
    ("Dependencies installed", True),
    ("agent.py imported", True),
    ("Simple query works", True),
    ("Cross-domain query works", True),
    ("Clarification works", True),
    ("MLflow logging works", True),
]

for check_name, status in checks:
    symbol = "✓" if status else "✗"
    print(f"{symbol} {check_name}")

print("\n" + "="*80)
print("✅ Notebook 05 completed successfully!")
print("Ready for deployment!")
print("="*80)
```

---

## Post-Test: Issues and Recommendations

### Known Issues to Watch For

1. **Vector Search Timing**
   - Index may take 5-10 minutes to be fully ready
   - First queries may be slower
   - **Solution:** Wait for ONLINE status, test queries before proceeding

2. **Agent Timeout**
   - Complex queries with multiple agents may timeout
   - **Solution:** Increase timeout, simplify query, or use async processing

3. **Genie Space Availability**
   - Genie spaces may be down or inaccessible
   - **Solution:** Verify space IDs, check Databricks Genie status

4. **Memory Issues**
   - Large responses or many parallel queries
   - **Solution:** Restart Python, clear cache, reduce num_results

### Common Error Patterns

#### Error: "Index not found"
```
Cause: Vector search index name mismatch
Solution: Verify index name matches in both notebooks
  - 04: Creates index as "{catalog}.{schema}.enriched_genie_docs_chunks_vs_index"
  - 05: agent.py references this name in vector search function
```

#### Error: "Function not found"
```
Cause: UC function name mismatch
Solution: Verify function name in agent.py matches created function:
  - Created in 04: yyang.multi_agent_genie.search_genie_spaces
  - Referenced in agent.py line 622
```

#### Error: "Genie space not accessible"
```
Cause: Invalid space ID or permissions
Solution:
  1. Verify space IDs in Databricks Genie UI
  2. Check you have access to each space
  3. Update space IDs in agent.py if needed
```

#### Error: "Embedding endpoint not found"
```
Cause: Embedding model endpoint doesn't exist
Solution:
  1. Check available endpoints: ChatDatabricks() endpoints
  2. Update embedding_model in 04 if needed
  3. Common options: "databricks-gte-large-en", "databricks-bge-large-en"
```

---

## Success Criteria

### Notebook 04 Success ✅
- [ ] Vector search endpoint created and ONLINE
- [ ] Delta sync index created and ONLINE
- [ ] Vector search queries return relevant results
- [ ] Filters work correctly (chunk_type, metadata)
- [ ] UC functions created and callable
- [ ] Test queries run successfully

### Notebook 05 Success ✅
- [ ] All dependencies installed
- [ ] agent.py imports without errors
- [ ] Simple single-space queries work
- [ ] Cross-domain queries with joins work
- [ ] Unclear questions trigger clarification
- [ ] Performance metrics acceptable (< 30s average)
- [ ] MLflow logging successful
- [ ] No critical errors in any test

### Overall System Health ✅
- [ ] End-to-end query flow works:
  - User question → ThinkingPlanning → Agent routing → SQL synthesis/execution → Response
- [ ] All 5 Genie spaces accessible
- [ ] Vector search finds relevant spaces correctly
- [ ] Agent makes appropriate routing decisions
- [ ] Responses are accurate and well-formatted

---

## Next Steps After Testing

### If All Tests Pass ✅
1. **Document Configuration**
   - Save current catalog, schema, and resource names
   - Document any custom configurations

2. **Optimize Performance**
   - Review slow queries
   - Consider adding more metadata to chunks
   - Tune vector search parameters

3. **Deploy to Production** (if ready)
   - Register model to Unity Catalog
   - Create model serving endpoint
   - Set up monitoring and logging

4. **Create User Documentation**
   - Example queries users can ask
   - Limitations and capabilities
   - How to interpret results

### If Tests Fail ⚠️
1. **Document Failures**
   - Which tests failed
   - Error messages
   - Screenshots if helpful

2. **Prioritize Fixes**
   - Critical: Vector search or agent import fails
   - High: Queries don't return results
   - Medium: Slow performance
   - Low: Clarification not perfect

3. **Request Help**
   - Share test results
   - Provide error logs
   - Explain what you've tried

---

## Testing Timeline Estimate

| Phase | Estimated Time | Can Parallelize |
|-------|---------------|-----------------|
| **Setup & Verification** | 10 minutes | No |
| **Notebook 04 - Vector Search** | 20-30 minutes | No (sequential steps) |
| **Notebook 05 - Agent System** | 30-40 minutes | Some (independent tests) |
| **Performance Testing** | 15-20 minutes | No |
| **Documentation** | 10 minutes | N/A |
| **Total** | **85-110 minutes** | |

**Factors that affect timing:**
- Index build time (depends on data size)
- LLM endpoint response time
- Genie space availability
- Your familiarity with Databricks

---

## Conclusion

This testing plan provides a comprehensive, step-by-step approach to validating both notebooks. Follow each test in sequence, document results, and address any issues before proceeding to deployment.

**Remember:**
- Test in a development environment first
- Document all configurations and results
- Don't skip tests even if earlier ones passed
- Performance tests are important for production readiness

**Good luck with testing! 🚀**

