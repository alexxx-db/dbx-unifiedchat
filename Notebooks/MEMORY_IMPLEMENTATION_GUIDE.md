# State Management Implementation Guide

## Overview

Your Super Agent has been enhanced with **two-tier memory system** to enable stateful conversations in distributed Databricks Model Serving:

1. **Short-term Memory (CheckpointSaver)** - CRITICAL for distributed serving
2. **Long-term Memory (DatabricksStore)** - Optional enhancement for user preferences

## ⚠️ Critical Issue Fixed

**Problem:** MemorySaver stored state in-memory (single process), causing multi-turn conversations to break in distributed Model Serving where each request can hit different instances.

**Solution:** CheckpointSaver stores state in Lakebase (PostgreSQL), making it accessible to all Model Serving instances.

## Changes Made

### 1. Package Dependencies

**Updated:** `Notebooks/Super_Agent_hybrid.py` (Line ~3)
```python
# OLD
%pip install databricks-langchain==0.12.1 databricks-vectorsearch==0.63

# NEW  
%pip install databricks-langchain[memory]==0.12.1 databricks-vectorsearch==0.63 databricks-agents mlflow-skinny[databricks]
```

**Updated:** `requirements.txt`
```txt
mlflow[databricks]>=3.6.0
databricks-langchain[memory]>=0.12.1  # Added [memory] extra
databricks-agents>=0.1.0
databricks-vectorsearch>=0.63
```

### 2. Configuration

**Added:** Lakebase configuration (Line ~54)
```python
# Lakebase configuration for state management
LAKEBASE_INSTANCE_NAME = "agent-state-db"  # TODO: Update with your instance name
EMBEDDING_ENDPOINT = "databricks-gte-large-en"
EMBEDDING_DIMS = 1024
```

### 3. Imports

**Added:** Memory-related imports (Line ~72)
```python
from databricks_langchain import (
    # ... existing imports ...
    CheckpointSaver,  # For short-term memory
    DatabricksStore,  # For long-term memory
)
from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
import logging
```

### 4. Agent State

**Added:** Memory fields to AgentState (Line ~390)
```python
class AgentState(TypedDict):
    # ... existing fields ...
    
    # State Management (NEW)
    user_id: Optional[str]  # User identifier for long-term memory
    thread_id: Optional[str]  # Thread identifier for short-term memory
    user_preferences: Optional[Dict]  # User preferences from long-term memory
```

### 5. Workflow Compilation

**Changed:** `create_super_agent_hybrid()` (Line ~2015)
```python
# OLD
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
return app

# NEW
app_graph = workflow  # Return uncompiled graph
return app_graph  # Checkpointer added at runtime
```

### 6. ResponsesAgent Class

**Completely Rewritten:** `SuperAgentHybridResponsesAgent` (Line ~2040)

**Key Changes:**
- Accepts `StateGraph` instead of `CompiledStateGraph`
- Added `DatabricksStore` for long-term memory (lazy initialization)
- Created 3 memory tools: `get_user_memory`, `save_user_memory`, `delete_user_memory`
- Added helper methods: `_get_or_create_thread_id()`, `_get_user_id()`
- Rewritten `predict_stream()` to use `CheckpointSaver` as context manager

**New Architecture:**
```python
class SuperAgentHybridResponsesAgent(ResponsesAgent):
    def __init__(self, workflow: StateGraph):
        self.workflow = workflow
        self._store = None  # Lazy init
        self._memory_tools = None  # Lazy init
    
    @property
    def store(self):
        """DatabricksStore for long-term memory"""
        
    @property
    def memory_tools(self):
        """Creates get/save/delete memory tools"""
    
    def predict_stream(self, request):
        # Use CheckpointSaver as context manager
        with CheckpointSaver(instance_name=LAKEBASE_INSTANCE_NAME) as checkpointer:
            app = self.workflow.compile(checkpointer=checkpointer)
            # Execute workflow...
```

## Setup Instructions

### Step 1: Create Lakebase Instance

1. Go to **SQL Warehouses → Lakebase Postgres → Create database instance**
2. Name your instance (e.g., `agent-state-db`)
3. Note the instance name for configuration

### Step 2: Update Configuration

Configuration is now centralized in `.env` file. Update the Lakebase settings:

**Edit `.env` file:**
```bash
# Lakebase Configuration (for State Management)
LAKEBASE_INSTANCE_NAME=your-actual-instance-name  # Update this!
LAKEBASE_EMBEDDING_ENDPOINT=databricks-gte-large-en
LAKEBASE_EMBEDDING_DIMS=1024
```

The notebook will automatically load these values from `config.py`.

### Step 3: Initialize Lakebase Tables (ONE-TIME)

Uncomment and run the setup cell in the notebook (Line ~103):
```python
from databricks_langchain import CheckpointSaver, DatabricksStore

# Setup checkpoint table
with CheckpointSaver(instance_name=LAKEBASE_INSTANCE_NAME) as saver:
    saver.setup()
    print("✓ Checkpoint table created")

# Setup store table
store = DatabricksStore(
    instance_name=LAKEBASE_INSTANCE_NAME,
    embedding_endpoint=EMBEDDING_ENDPOINT,
    embedding_dims=EMBEDDING_DIMS,
)
store.setup()
print("✓ Store table created")
```

### Step 4: Test Locally

#### Short-term Memory Test
```python
from mlflow.types.responses import ResponsesAgentRequest
import uuid

thread_id = str(uuid.uuid4())

# Message 1
result1 = AGENT.predict(ResponsesAgentRequest(
    input=[{"role": "user", "content": "Show me patient data"}],
    custom_inputs={"thread_id": thread_id}
))

# Message 2 - agent remembers context
result2 = AGENT.predict(ResponsesAgentRequest(
    input=[{"role": "user", "content": "Filter by age > 50"}],
    custom_inputs={"thread_id": thread_id}  # Same thread_id
))
```

#### Long-term Memory Test
```python
from mlflow.types.responses import ChatContext

# Save preference
result1 = AGENT.predict(ResponsesAgentRequest(
    input=[{"role": "user", "content": "I prefer bar charts"}],
    context=ChatContext(
        conversation_id=str(uuid.uuid4()),
        user_id="user@example.com"
    )
))

# In new session, recall preference
result2 = AGENT.predict(ResponsesAgentRequest(
    input=[{"role": "user", "content": "Show me data"}],
    context=ChatContext(
        conversation_id=str(uuid.uuid4()),  # Different session
        user_id="user@example.com"  # Same user
    )
))
```

### Step 5: Deploy to Model Serving

```python
from mlflow.models.resources import DatabricksLakebase, DatabricksServingEndpoint
from databricks import agents

resources = [
    DatabricksServingEndpoint(LLM_ENDPOINT_CLARIFICATION),
    DatabricksServingEndpoint(LLM_ENDPOINT_PLANNING),
    DatabricksServingEndpoint(LLM_ENDPOINT_SQL_SYNTHESIS),
    DatabricksServingEndpoint(LLM_ENDPOINT_SUMMARIZE),
    DatabricksServingEndpoint(EMBEDDING_ENDPOINT),
    DatabricksLakebase(database_instance_name=LAKEBASE_INSTANCE_NAME),  # CRITICAL!
    # ... other resources ...
]

with mlflow.start_run():
    logged_agent_info = mlflow.pyfunc.log_model(
        name="super_agent_hybrid_with_memory",
        python_model="Super_Agent_hybrid.py",
        input_example=input_example,
        resources=resources,
        pip_requirements=[
            "databricks-langchain[memory]>=0.12.1",
            "databricks-agents>=0.1.0",
            "mlflow[databricks]>=3.6.0",
        ]
    )

# Register and deploy
mlflow.set_registry_uri("databricks-uc")
UC_MODEL_NAME = f"{CATALOG}.{SCHEMA}.super_agent_hybrid"
uc_model_info = mlflow.register_model(logged_agent_info.model_uri, UC_MODEL_NAME)

agents.deploy(UC_MODEL_NAME, uc_model_info.version)
```

## API Usage

### Multi-turn Conversation (Short-term Memory)

```bash
# Request 1
curl -X POST https://workspace.databricks.com/serving-endpoints/super-agent/invocations \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "messages": [{"role": "user", "content": "Show me patient data"}],
    "custom_inputs": {"thread_id": "session_123"}
  }'

# Request 2 (remembers context)
curl -X POST https://workspace.databricks.com/serving-endpoints/super-agent/invocations \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "messages": [{"role": "user", "content": "Filter by age > 50"}],
    "custom_inputs": {"thread_id": "session_123"}
  }'
```

### With User Preferences (Long-term Memory)

```bash
curl -X POST https://workspace.databricks.com/serving-endpoints/super-agent/invocations \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "messages": [{"role": "user", "content": "Show me data"}],
    "context": {
      "conversation_id": "sess_456",
      "user_id": "user@example.com"
    }
  }'
```

## Monitoring

### Query Checkpoints (Short-term Memory)

```sql
-- View recent conversation checkpoints
SELECT 
    thread_id,
    checkpoint_id,
    (checkpoint::json->>'ts')::timestamptz AS timestamp,
    parent_checkpoint_id
FROM checkpoints
ORDER BY timestamp DESC
LIMIT 20;
```

### Query User Memories (Long-term Memory)

```sql
-- View stored user preferences
SELECT 
    namespace,
    key,
    value,
    updated_at
FROM public.store
WHERE namespace LIKE '%user_memories%'
ORDER BY updated_at DESC
LIMIT 50;
```

## Benefits

### ✅ Short-term Memory (CheckpointSaver)
- Works in distributed Model Serving (multiple instances)
- Multi-turn conversations preserved across requests
- Clarification flow works correctly
- Automatic connection pooling and credential rotation
- No manual state management needed

### ⭐ Long-term Memory (DatabricksStore)
- User preferences remembered across sessions
- Semantic search with vector embeddings
- Personalized experiences
- Agent can learn user patterns over time

## Troubleshooting

### Issue: "Memory not available - no user_id provided"
**Solution:** Pass `user_id` via `ChatContext` or `custom_inputs`

### Issue: Multi-turn conversations not working
**Solution:** 
1. Verify Lakebase instance is running
2. Check `LAKEBASE_INSTANCE_NAME` is correct
3. Ensure setup cell was run to create tables
4. Verify `DatabricksLakebase` resource is in deployment resources

### Issue: Lakebase connection errors
**Solution:**
1. Check Lakebase instance status in SQL Warehouses
2. Verify network connectivity from Model Serving to Lakebase
3. Ensure automatic authentication is configured (via resources)

## Next Steps

1. ✅ **Test locally** with provided examples
2. ✅ **Deploy to Model Serving** with DatabricksLakebase resource
3. ✅ **Test distributed serving** - verify multi-turn works across instances
4. ⭐ **Monitor usage** - query checkpoints and store tables
5. ⭐ **Optimize** - implement checkpoint TTL for cleanup

## References

- [Databricks AI Agent Memory Documentation](https://docs.databricks.com/aws/en/generative-ai/agent-framework/stateful-agents)
- [Short-term Memory Agent Example](https://docs.databricks.com/aws/en/notebooks/source/generative-ai/short-term-memory-agent-lakebase.html)
- [Long-term Memory Agent Example](https://docs.databricks.com/aws/en/notebooks/source/generative-ai/long-term-memory-agent-lakebase.html)
- [Lakebase Documentation](https://databricks.com/resources/demos/videos/lakebase-real-time-operation-and-analytical-data-one-platform)
