# Migration Guide: Legacy to Modern Agent Deployment

Quick reference guide for migrating from legacy patterns to modern `databricks-agents>=0.13.0` and modern LangGraph patterns.

---

## Quick Reference Table

| Task | Legacy Pattern | Modern Pattern |
|------|---------------|----------------|
| Install packages | `langgraph-supervisor==0.0.30` | `langgraph langgraph-checkpoint` |
| Agents SDK | `databricks-agents` (any) | `databricks-agents>=0.13.0` |
| Create supervisor | `create_supervisor()` | `StateGraph()` |
| Deploy model | 4+ separate steps | `agents.deploy()` |
| Query endpoint | `w.serving_endpoints.query()` | `deployment.predict()` |
| Load deployment | Manual endpoint lookup | `agents.get_deployment()` |

---

## 1. Package Installation

### ❌ Legacy
```python
%pip install -U -qqq langgraph-supervisor==0.0.30 \
    mlflow[databricks] \
    databricks-langchain \
    databricks-agents \
    databricks-vectorsearch
```

### ✅ Modern
```python
%pip install -U -qqq langgraph \
    langgraph-checkpoint \
    mlflow[databricks]>=2.18.0 \
    databricks-langchain \
    databricks-agents>=0.13.0 \
    databricks-vectorsearch
```

**Why?**
- `langgraph-supervisor` is deprecated → use core `langgraph`
- Modern `databricks-agents>=0.13.0` has simplified deployment APIs

---

## 2. Imports

### ❌ Legacy
```python
from langgraph_supervisor import create_supervisor
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)
from langgraph.graph.state import CompiledStateGraph
```

### ✅ Modern
```python
from langgraph.graph import StateGraph, MessagesState
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_tool_calling_agent
```

---

## 3. Creating Agent Graph

### ❌ Legacy
```python
def create_langgraph_supervisor(llm, agents_list, prompt):
    return create_supervisor(
        agents=agents_list,
        model=llm,
        prompt=prompt,
        add_handoff_messages=False,
        output_mode="full_history",
    ).compile()
```

### ✅ Modern
```python
def create_langgraph_supervisor(llm, agents_dict, prompt):
    workflow = StateGraph(MessagesState)
    
    # Add supervisor routing
    def supervisor_node(state):
        # Your routing logic
        return {"next": "agent_name"}
    
    workflow.add_node("supervisor", supervisor_node)
    
    # Add agent nodes
    for name, agent in agents_dict.items():
        workflow.add_node(name, lambda s, a=agent: a(s))
    
    # Set entry and edges
    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges("supervisor", route_function)
    
    # Compile with memory
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
```

**Benefits:**
- More explicit control
- Better state management
- Easier to debug
- Built-in memory support

---

## 4. Model Deployment

### ❌ Legacy (Multi-Step)

```python
# Step 1: Start MLflow run and log model
with mlflow.start_run(run_name="my_agent") as run:
    signature = infer_signature(test_input, test_output)
    mlflow.pyfunc.log_model(
        artifact_path="agent",
        python_model=AGENT,
        signature=signature,
        pip_requirements=[...],
        code_paths=["agent.py"],
    )
    run_id = run.info.run_id
    model_uri = f"runs:/{run_id}/agent"

# Step 2: Register model
model_version = mlflow.register_model(
    model_uri=model_uri,
    name="my_agent_model"
)

# Step 3: Create/update serving endpoint
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput
)

w = WorkspaceClient()

try:
    w.serving_endpoints.update_config_and_wait(
        name="my-agent-endpoint",
        served_entities=[
            ServedEntityInput(
                entity_name="my_agent_model",
                entity_version=model_version.version,
                scale_to_zero_enabled=True,
                workload_size="Small",
            )
        ],
    )
except:
    w.serving_endpoints.create_and_wait(
        name="my-agent-endpoint",
        config=EndpointCoreConfigInput(
            served_entities=[...]
        ),
    )

# Step 4: Test endpoint
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

response = w.serving_endpoints.query(
    name="my-agent-endpoint",
    messages=[
        ChatMessage(
            role=ChatMessageRole.USER,
            content="Test question"
        )
    ],
)
```

### ✅ Modern (Single Step)

```python
from databricks import agents

# One command does everything!
deployment = agents.deploy(
    model_uri="agent.py",
    model_name="my_agent_model",
    endpoint_name="my-agent-endpoint",
    
    # Configuration
    model_config={
        "llm_endpoint": "databricks-claude-sonnet-4-5",
    },
    
    environment_vars={
        "LLM_ENDPOINT": "databricks-claude-sonnet-4-5",
    },
    
    # Deployment settings
    scale_to_zero_enabled=True,
    workload_size="Small",
    python_version="3.11",
)

# Test immediately
response = deployment.predict(
    messages=[{"role": "user", "content": "Test question"}]
)
```

**Line count reduction:** ~60 lines → ~20 lines (67% reduction!)

---

## 5. Querying Deployed Agent

### ❌ Legacy
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

w = WorkspaceClient()

response = w.serving_endpoints.query(
    name="my-agent-endpoint",
    messages=[
        ChatMessage(
            role=ChatMessageRole.USER,
            content="Your question here"
        )
    ],
)
```

### ✅ Modern
```python
from databricks import agents

# Option 1: Use existing deployment object
response = deployment.predict(
    messages=[{"role": "user", "content": "Your question here"}]
)

# Option 2: Load deployment by name
deployment = agents.get_deployment("my-agent-endpoint")
response = deployment.predict(
    messages=[{"role": "user", "content": "Your question here"}]
)
```

---

## 6. Testing Pattern

### ❌ Legacy
```python
# Complex streaming with event handling
for event in AGENT.predict_stream(input_example):
    result = event.model_dump(exclude_none=True)
    if event.type == "response.output_item.done":
        print(result)
```

### ✅ Modern
```python
# Simple synchronous testing
response = deployment.predict(
    messages=[{"role": "user", "content": test_query}]
)
print(response)

# Or local testing with agent graph
result = agent_graph.invoke({"messages": messages})
```

---

## 7. Production Usage

### ❌ Legacy
```python
def query_agent(question):
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
    
    w = WorkspaceClient()
    
    response = w.serving_endpoints.query(
        name="my-agent-endpoint",
        messages=[
            ChatMessage(
                role=ChatMessageRole.USER,
                content=question
            )
        ],
    )
    
    return response
```

### ✅ Modern
```python
def query_agent(question, endpoint_name="my-agent-endpoint"):
    from databricks import agents
    
    deployment = agents.get_deployment(endpoint_name)
    response = deployment.predict(
        messages=[{"role": "user", "content": question}]
    )
    
    return response
```

---

## 8. Agent Wrapper Class

### ❌ Legacy
```python
class LangGraphResponsesAgent(ResponsesAgent):
    def __init__(self, agent: CompiledStateGraph):
        self.agent = agent

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        outputs = [
            event.item
            for event in self.predict_stream(request)
            if event.type == "response.output_item.done"
        ]
        return ResponsesAgentResponse(output=outputs)

    def predict_stream(self, request):
        cc_msgs = to_chat_completions_input(...)
        seen_ids = set()
        # 30+ lines of complex streaming logic
        ...

# Usage
AGENT = LangGraphResponsesAgent(supervisor)
mlflow.models.set_model(AGENT)
```

### ✅ Modern
```python
class MultiAgentSystem:
    def __init__(self, graph):
        self.graph = graph
        self.config = {"configurable": {"thread_id": "default"}}

    def predict(self, input_dict):
        messages = [
            HumanMessage(content=msg["content"]) 
            for msg in input_dict["input"]
        ]
        result = self.graph.invoke({"messages": messages})
        return {"messages": [...]}

# Usage
AGENT = MultiAgentSystem(supervisor_graph)
# No need to set_model when using agents.deploy()
```

---

## 9. Complete Migration Example

### ❌ Legacy Complete Flow
```python
# 1. Install
%pip install langgraph-supervisor==0.0.30 databricks-agents

# 2. Create supervisor
from langgraph_supervisor import create_supervisor
supervisor = create_supervisor(agents=agent_list, model=llm, prompt=prompt)

# 3. Wrap
from mlflow.pyfunc import ResponsesAgent
AGENT = LangGraphResponsesAgent(supervisor)

# 4. Log
with mlflow.start_run() as run:
    mlflow.pyfunc.log_model(...)
    run_id = run.info.run_id

# 5. Register
mlflow.register_model(model_uri=f"runs:/{run_id}/agent", name="model")

# 6. Deploy
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
w.serving_endpoints.create_and_wait(...)

# 7. Query
response = w.serving_endpoints.query(...)
```

### ✅ Modern Complete Flow
```python
# 1. Install
%pip install langgraph databricks-agents>=0.13.0

# 2. Create graph
from langgraph.graph import StateGraph
workflow = StateGraph(MessagesState)
# ... add nodes and edges
graph = workflow.compile(checkpointer=MemorySaver())

# 3. Deploy (combines steps 4-6 from legacy)
from databricks import agents
deployment = agents.deploy(
    model_uri="agent.py",
    model_name="model",
    endpoint_name="endpoint",
)

# 4. Query
response = deployment.predict(
    messages=[{"role": "user", "content": "Question"}]
)
```

**Steps reduced:** 7 → 4 (43% reduction!)

---

## Common Migration Issues

### Issue 1: Missing `create_supervisor`

**Error:**
```
ImportError: cannot import name 'create_supervisor' from 'langgraph_supervisor'
```

**Solution:**
Replace with `StateGraph`:
```python
from langgraph.graph import StateGraph, MessagesState

workflow = StateGraph(MessagesState)
# ... build graph manually
graph = workflow.compile()
```

### Issue 2: `ResponsesAgent` not needed

**Error:**
```
Module 'mlflow.pyfunc' has no attribute 'ResponsesAgent'
```

**Solution:**
You don't need custom wrapper classes with modern `agents.deploy()`:
```python
# Just use agents.deploy() directly on your agent.py module
deployment = agents.deploy(model_uri="agent.py", ...)
```

### Issue 3: Query format mismatch

**Error:**
```
AttributeError: 'dict' object has no attribute 'role'
```

**Solution:**
Use simple dict format:
```python
# ❌ Old: ChatMessage objects
messages=[ChatMessage(role=ChatMessageRole.USER, content="Hi")]

# ✅ New: Simple dicts
messages=[{"role": "user", "content": "Hi"}]
```

---

## Testing Your Migration

Run this checklist after migrating:

```python
# 1. Can you import modern packages?
from langgraph.graph import StateGraph, MessagesState
from databricks import agents
print("✓ Imports work")

# 2. Can you create a graph?
workflow = StateGraph(MessagesState)
# ... add nodes
graph = workflow.compile()
print("✓ Graph creation works")

# 3. Can you deploy?
try:
    deployment = agents.deploy(
        model_uri="agent.py",
        model_name="test_model",
        endpoint_name="test-endpoint",
    )
    print("✓ Deployment works")
except Exception as e:
    print(f"✗ Deployment failed: {e}")

# 4. Can you query?
try:
    response = deployment.predict(
        messages=[{"role": "user", "content": "test"}]
    )
    print("✓ Query works")
except Exception as e:
    print(f"✗ Query failed: {e}")
```

---

## Benefits Checklist

After migration, you should see:

- ✅ Fewer lines of code (typically 50-70% reduction)
- ✅ Simpler deployment process (1 command vs 4+)
- ✅ Better error messages
- ✅ Integrated monitoring and tracing
- ✅ Easier testing workflow
- ✅ Future-proof with maintained packages
- ✅ Standard message format across projects

---

## Need Help?

1. **Check documentation:**
   - [Databricks Agents SDK](https://docs.databricks.com/en/generative-ai/agents-sdk.html)
   - [LangGraph Docs](https://langchain-ai.github.io/langgraph/)

2. **Review examples:**
   - See `Notebooks/05_Multi_Agent_System.py` for complete example
   - See `Notebooks/agent.py` for graph implementation

3. **Common patterns:**
   - Use `StateGraph` for supervisor logic
   - Use `agents.deploy()` for deployment
   - Use `deployment.predict()` for queries

---

**Last Updated:** December 5, 2025

