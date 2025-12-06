# MLflow 3.7.0 Refactoring Guide

## Overview

This document describes the refactoring to support **MLflow 3.7.0** with proper `PythonModel` implementation for serving LangGraph-based multi-agent systems.

**Date:** December 5, 2025  
**MLflow Version:** 3.7.0  
**Key Changes:** Added PythonModel wrapper, ChatResponse format, proper serving interface

---

## Why MLflow 3.7.0?

MLflow 3.7.0 introduces several critical features for agent serving:

1. **Enhanced Tracing**: Trace comparison and multi-turn conversation support
2. **Full-text Search**: Search traces from the UI
3. **Better Agent Support**: Improved patterns for serving generative AI agents
4. **ChatResponse Format**: Structured response format with choices and messages
5. **PythonModel Interface**: Proper serving with `load_context()` and `predict()` methods

---

## Key Architectural Changes

### 1. PythonModel Implementation

**New Class: `LangGraphChatModel`**

```python
from mlflow.pyfunc import PythonModel
from mlflow.types.llm import ChatMessage, ChatResponse, ChatChoice

class LangGraphChatModel(PythonModel):
    """MLflow 3.7.0 compatible wrapper for LangGraph multi-agent system."""
    
    def __init__(self, graph=None):
        self.graph = graph
        self.config = {"configurable": {"thread_id": "default"}}
    
    def load_context(self, context):
        """Load the agent graph when model is loaded."""
        if self.graph is None:
            self.graph = get_agent_graph()
    
    def predict(self, context, model_input, params=None):
        """Main prediction method for MLflow 3.7.0."""
        # Convert input messages
        messages = model_input.get("messages", [])
        langchain_messages = self._convert_messages(messages)
        
        # Invoke graph
        result = self.graph.invoke(
            {"messages": langchain_messages},
            config=self.config
        )
        
        # Return ChatResponse
        return ChatResponse(
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(
                        role="assistant",
                        content=self._extract_response(result)
                    )
                )
            ]
        )
```

**Why PythonModel?**
- Required by MLflow 3.7.0 for proper model serving
- Provides `load_context()` for initialization
- Returns structured `ChatResponse` objects
- Compatible with MLflow's serving infrastructure

---

## Input/Output Formats

### Input Format (MLflow 3.7.0)

```python
{
    "messages": [
        {"role": "user", "content": "How many patients are over 65?"}
    ]
}
```

### Output Format (ChatResponse)

```python
ChatResponse(
    choices=[
        ChatChoice(
            index=0,
            message=ChatMessage(
                role="assistant",
                content="Based on the data, there are 1,234 patients over 65 years old."
            )
        )
    ]
)
```

**Benefits:**
- Structured format for consistency
- Support for multiple choices (future extensions)
- Standard message format (role + content)
- Compatible with OpenAI-style APIs

---

## Deployment Pattern

### Step 1: Log Model with MLflow 3.7.0

```python
import mlflow
from mlflow.models import infer_signature

# Create model instance
from agent import MLFLOW_MODEL

# Create signature
sample_input = {
    "messages": [{"role": "user", "content": "Test"}]
}
sample_output = MLFLOW_MODEL.predict(context=None, model_input=sample_input)
signature = infer_signature(sample_input, sample_output)

# Log model
with mlflow.start_run() as run:
    mlflow.pyfunc.log_model(
        artifact_path="agent",
        python_model=MLFLOW_MODEL,  # PythonModel instance
        signature=signature,
        input_example=sample_input,
        pip_requirements=[
            "mlflow[databricks]==3.7.0",
            "langgraph",
            "langgraph-checkpoint",
            "databricks-langchain",
            "databricks-agents>=0.13.0",
            "databricks-vectorsearch",
        ],
        code_paths=["agent.py"],
        registered_model_name="multi_agent_genie_system",
    )
    
    model_uri = f"runs:/{run.info.run_id}/agent"
```

### Step 2: Deploy to Endpoint

```python
from databricks import agents

deployment = agents.deploy(
    model_uri=model_uri,
    endpoint_name="multi-agent-genie-endpoint",
    scale_to_zero_enabled=True,
    workload_size="Small",
)
```

### Step 3: Query Endpoint

```python
# Query deployed endpoint
response = deployment.predict(
    inputs={
        "messages": [
            {"role": "user", "content": "Your question here"}
        ]
    }
)

# Extract response text
response_text = response.choices[0].message.content
print(response_text)
```

---

## Dual Wrapper Pattern

The code now provides **two wrapper classes**:

### 1. `LangGraphChatModel` (For Production)

```python
MLFLOW_MODEL = LangGraphChatModel(graph=supervisor_graph)

# Set for MLflow deployment
mlflow.models.set_model(MLFLOW_MODEL)
```

**Use for:**
- MLflow logging and serving
- Production deployment
- Endpoint serving

**Returns:** `ChatResponse` objects

### 2. `MultiAgentSystem` (For Testing)

```python
AGENT = MultiAgentSystem(supervisor_graph)

# Use for local testing
response = AGENT.predict({
    "input": [{"role": "user", "content": "Test"}]
})
```

**Use for:**
- Local development and testing
- Notebook testing
- Quick iterations

**Returns:** Dictionary with messages

---

## Testing Patterns

### Local Testing (Before Deployment)

```python
from agent import MLFLOW_MODEL

# Test locally
response = MLFLOW_MODEL.predict(
    context=None,
    model_input={
        "messages": [
            {"role": "user", "content": "How many patients?"}
        ]
    }
)

print(response.choices[0].message.content)
```

### Testing Deployed Endpoint

```python
from databricks import agents

# Get deployment
deployment = agents.get_deployment("multi-agent-genie-endpoint")

# Query
response = deployment.predict(
    inputs={
        "messages": [
            {"role": "user", "content": "How many patients?"}
        ]
    }
)

print(response.choices[0].message.content)
```

### Notebook Testing (Direct Graph)

```python
from agent import AGENT

# Test with simplified wrapper
response = AGENT.predict({
    "input": [{"role": "user", "content": "How many patients?"}]
})

print(response["messages"][-1]["content"])
```

---

## File Changes Summary

### `agent.py`

**Added:**
1. MLflow 3.7.0 imports:
   ```python
   from mlflow.pyfunc import PythonModel
   from mlflow.types.llm import ChatMessage, ChatResponse, ChatChoice
   ```

2. `LangGraphChatModel` class (150+ lines)
   - Implements `PythonModel` interface
   - `load_context()` method
   - `predict()` method with ChatResponse
   - Helper methods for message conversion

3. Dual wrapper instantiation:
   ```python
   AGENT = MultiAgentSystem(supervisor_graph)  # Testing
   MLFLOW_MODEL = LangGraphChatModel(graph=supervisor_graph)  # Production
   mlflow.models.set_model(MLFLOW_MODEL)
   ```

### `05_Multi_Agent_System.py`

**Updated:**
1. Package installation:
   ```python
   %pip install mlflow[databricks]==3.7.0
   ```

2. Deployment section:
   - Uses `mlflow.pyfunc.log_model()` with `MLFLOW_MODEL`
   - Includes signature inference
   - Registers model during logging
   - Deploys with `agents.deploy()`

3. Testing patterns:
   - Local testing with `MLFLOW_MODEL`
   - Endpoint testing with `deployment.predict(inputs=...)`
   - Performance testing with multiple modes

4. Documentation:
   - Updated usage guide
   - Added MLflow 3.7.0 patterns
   - Documented ChatResponse format

---

## Message Flow

```
User Input
    ↓
{"messages": [{"role": "user", "content": "..."}]}
    ↓
LangGraphChatModel.predict()
    ↓
_convert_messages() → [HumanMessage(...)]
    ↓
graph.invoke({"messages": [...]})
    ↓
_extract_response() → "response text"
    ↓
ChatResponse(choices=[ChatChoice(message=ChatMessage(...))])
    ↓
User receives structured response
```

---

## Migration Checklist

If updating from an older version:

- [ ] Update MLflow to 3.7.0: `pip install mlflow[databricks]==3.7.0`
- [ ] Add PythonModel imports to `agent.py`
- [ ] Implement `LangGraphChatModel` class
- [ ] Update `predict()` to return `ChatResponse`
- [ ] Create dual wrappers (AGENT + MLFLOW_MODEL)
- [ ] Update deployment to use `mlflow.pyfunc.log_model()`
- [ ] Update query pattern to use `inputs={"messages": [...]}`
- [ ] Test locally before deploying
- [ ] Update documentation and examples

---

## Benefits of MLflow 3.7.0 Pattern

### For Developers
- ✅ **Proper serving interface**: PythonModel with load_context
- ✅ **Structured responses**: ChatResponse format
- ✅ **Better testing**: Can test locally before deploying
- ✅ **Type safety**: Structured message and response types

### For Operations
- ✅ **Enhanced tracing**: MLflow 3.7.0 tracing features
- ✅ **Multi-turn support**: Conversation tracking
- ✅ **Better monitoring**: Full-text trace search
- ✅ **Standard format**: Compatible with OpenAI-style APIs

### For Users
- ✅ **Consistent responses**: Structured ChatResponse format
- ✅ **Better error handling**: Proper error messages in responses
- ✅ **Conversation support**: Multi-turn conversations tracked
- ✅ **Production-ready**: Following MLflow best practices

---

## Common Issues and Solutions

### Issue 1: Import Error for ChatResponse

**Error:**
```python
ImportError: cannot import name 'ChatResponse' from 'mlflow.types.llm'
```

**Solution:**
Ensure MLflow 3.7.0 is installed:
```bash
pip install mlflow[databricks]==3.7.0
```

### Issue 2: predict() Signature Mismatch

**Error:**
```python
TypeError: predict() missing 1 required positional argument: 'model_input'
```

**Solution:**
PythonModel.predict() requires `context` parameter:
```python
def predict(self, context, model_input, params=None):
    # context is required even if unused
    ...
```

### Issue 3: Wrong Response Format

**Error:**
```python
AttributeError: 'dict' object has no attribute 'choices'
```

**Solution:**
Ensure you're returning `ChatResponse`:
```python
return ChatResponse(
    choices=[
        ChatChoice(
            index=0,
            message=ChatMessage(role="assistant", content=text)
        )
    ]
)
```

### Issue 4: Deployment Input Format

**Error:**
```python
KeyError: 'messages'
```

**Solution:**
Use correct input format with `inputs` wrapper:
```python
# ❌ Wrong
deployment.predict(messages=[...])

# ✅ Correct
deployment.predict(inputs={"messages": [...]})
```

---

## Performance Considerations

### Memory Usage
- **PythonModel**: Slightly higher memory due to graph caching
- **Mitigation**: Use scale-to-zero-enabled endpoints

### Latency
- **First request**: May be slower due to graph initialization
- **Subsequent requests**: Fast with warmed-up endpoint
- **Recommendation**: Keep endpoints warm during high-traffic periods

### Tracing Overhead
- **MLflow 3.7.0 tracing**: Minimal overhead (<5ms per request)
- **Benefits**: Worth the overhead for debugging and monitoring

---

## Best Practices

### 1. Always Test Locally First

```python
from agent import MLFLOW_MODEL

# Test before deploying
response = MLFLOW_MODEL.predict(
    context=None,
    model_input={"messages": [...]}
)
assert isinstance(response, ChatResponse)
```

### 2. Use Proper Error Handling

```python
def predict(self, context, model_input, params=None):
    try:
        result = self.graph.invoke(...)
        return ChatResponse(...)
    except Exception as e:
        # Return error as ChatResponse
        return ChatResponse(
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(
                        role="assistant",
                        content=f"Error: {str(e)}"
                    )
                )
            ]
        )
```

### 3. Log Comprehensive Traces

```python
# Enable autologging
mlflow.langchain.autolog()

# Log with detailed metadata
with mlflow.start_run() as run:
    mlflow.log_params({"version": "2.0", "mlflow": "3.7.0"})
    mlflow.pyfunc.log_model(...)
```

### 4. Monitor Endpoint Health

```python
# Regular health checks
try:
    response = deployment.predict(
        inputs={"messages": [{"role": "user", "content": "health"}]}
    )
    print("Endpoint healthy" if response.choices else "Endpoint issues")
except Exception as e:
    print(f"Endpoint error: {e}")
```

---

## Future Enhancements

Possible improvements with MLflow 3.7.0:

1. **Streaming Responses**: Implement streaming with yield
2. **Tool Calling**: Leverage MLflow 3.7.0 tool support
3. **Conversation Memory**: Use thread_id for multi-turn conversations
4. **A/B Testing**: Deploy multiple versions with traffic splitting
5. **Advanced Tracing**: Custom trace attributes and metrics

---

## Resources

- [MLflow 3.7.0 Release Notes](https://github.com/mlflow/mlflow/releases/tag/v3.7.0)
- [MLflow PythonModel Documentation](https://mlflow.org/docs/latest/python_api/mlflow.pyfunc.html)
- [Databricks Agents SDK](https://docs.databricks.com/en/generative-ai/agents-sdk.html)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)

---

## Support

For issues with MLflow 3.7.0 integration:

1. **Check MLflow version**: `pip show mlflow`
2. **Review logs**: Check MLflow UI for traces
3. **Test locally**: Use `MLFLOW_MODEL.predict()` before deploying
4. **Verify format**: Ensure input/output follows ChatResponse pattern

---

**Last Updated:** December 5, 2025  
**MLflow Version:** 3.7.0  
**Status:** ✅ Production Ready

