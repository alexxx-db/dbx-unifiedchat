# StructuredTool Function Signature Fix - Complete

## Critical Issue Fixed
Error: `_genie_tool_call() got an unexpected keyword argument 'question'`

This error occurred in **BOTH** serial and parallel execution.

## Root Cause

When using `StructuredTool` with `args_schema`, LangChain expects the function to accept **individual field arguments as kwargs**, NOT a single Pydantic object.

### Wrong Pattern (What We Had)
```python
class GenieToolInput(BaseModel):
    question: str = Field(...)
    conversation_id: Optional[str] = Field(None)

def _genie_tool_call(args: GenieToolInput):  # ❌ WRONG!
    agent.invoke({
        "messages": [{"role": "user", "content": args.question}],
        "conversation_id": args.conversation_id,
    })

genie_tool = StructuredTool(
    name="Genie_Sales",
    args_schema=GenieToolInput,
    func=_genie_tool_call,  # Function expects single Pydantic arg
)

# When LangChain calls the tool:
# tool.func(question="...", conversation_id=...)  # Unpacks as kwargs
# But function expects: tool.func(GenieToolInput(...))  # Single object
# Result: ❌ TypeError: got unexpected keyword argument 'question'
```

### Correct Pattern (Fixed)
```python
class GenieToolInput(BaseModel):
    question: str = Field(...)
    conversation_id: Optional[str] = Field(None)

def _genie_tool_call(question: str, conversation_id: Optional[str] = None):  # ✅ CORRECT!
    """
    StructuredTool with args_schema expects individual field arguments,
    not a single Pydantic object.
    """
    agent.invoke({
        "messages": [{"role": "user", "content": question}],
        "conversation_id": conversation_id,
    })

genie_tool = StructuredTool(
    name="Genie_Sales",
    args_schema=GenieToolInput,  # Defines schema for validation
    func=_genie_tool_call,  # Function accepts individual kwargs
)

# When LangChain calls the tool:
# tool.func(question="...", conversation_id=...)  # Unpacks as kwargs
# Function expects: (question, conversation_id)  # Individual args
# Result: ✅ Works perfectly!
```

## The Fix Applied

### 1. Fixed Individual Tool Function Signature
Changed from accepting a Pydantic object to accepting individual kwargs:

```python
# BEFORE (broken):
def _genie_tool_call(args: GenieToolInput):
    result = agent.invoke({
        "messages": [{"role": "user", "content": args.question}],
        "conversation_id": args.conversation_id,
    })

# AFTER (fixed):
def _genie_tool_call(question: str, conversation_id: Optional[str] = None):
    result = agent.invoke({
        "messages": [{"role": "user", "content": question}],
        "conversation_id": conversation_id,
    })
```

### 2. Updated Parallel Execution to Pass Individual Args
Changed from creating Pydantic objects to passing individual kwargs:

```python
# BEFORE (broken):
parallel_tasks[space_id] = RunnableLambda(
    lambda inp, sid=space_id, t=tool: t.func(
        GenieToolInput(question=inp[sid], conversation_id=None)
    )
)

# AFTER (fixed):
parallel_tasks[space_id] = RunnableLambda(
    lambda inp, sid=space_id, t=tool: t.func(
        question=inp[sid], conversation_id=None
    )
)
```

### 3. Removed Unnecessary GenieToolInput Definitions
Since we're passing individual kwargs now, we don't need to create GenieToolInput objects in the parallel execution code.

## Why This Happens

LangChain's `StructuredTool` with `args_schema` works like this:

1. **Schema Definition**: `args_schema=GenieToolInput` tells LangChain:
   - What fields the tool accepts
   - Their types
   - Validation rules
   - Descriptions for LLM

2. **LLM Tool Call**: When LLM calls the tool, it provides:
   ```json
   {
     "name": "Genie_Sales",
     "arguments": {
       "question": "Get sales data",
       "conversation_id": null
     }
   }
   ```

3. **LangChain Validation**: 
   - Creates `GenieToolInput(question="Get sales data", conversation_id=None)`
   - Validates against schema
   - **Then unpacks it as kwargs** to call the function

4. **Function Invocation**:
   ```python
   # LangChain does this internally:
   validated_input = GenieToolInput(**llm_arguments)  # Validate
   result = tool.func(**validated_input.dict())  # Unpack and call
   ```

5. **Your Function Must Accept**:
   ```python
   def _genie_tool_call(question: str, conversation_id: Optional[str] = None):
       # Receives individual kwargs, not Pydantic object!
   ```

## Files Modified

1. **`Notebooks/Super_Agent_hybrid.py`**
   - Line ~1326: Fixed `_genie_tool_call` signature (serial execution)
   - Line ~1485: Updated parallel execution in `_create_parallel_execution_tool()`
   - Line ~1658: Updated parallel execution in `invoke_genie_agents_parallel()`
   - Removed unnecessary `GenieToolInput` definitions in parallel methods

## Impact

### ✅ Fixed: Serial Tool Invocation
```python
# Agent calls individual tool
sql_synthesis_agent.invoke({"messages": [...]})
# LangChain internally:
# - Validates: GenieToolInput(question="...", conversation_id=None)
# - Calls: tool.func(question="...", conversation_id=None)
# - Function receives: _genie_tool_call(question, conversation_id)
# Result: ✅ Works!
```

### ✅ Fixed: Parallel Tool Invocation
```python
# Manual parallel execution
parallel_tasks[sid] = RunnableLambda(
    lambda inp, t=tool: t.func(question=inp[sid], conversation_id=None)
)
# Function receives: _genie_tool_call(question, conversation_id)
# Result: ✅ Works!
```

## Key Takeaways

### ✅ DO:
- Use individual field arguments when defining StructuredTool functions
- Match function signature to Pydantic schema fields
- Let LangChain handle Pydantic validation and unpacking
- Pass individual kwargs when calling tool.func() manually

### ❌ DON'T:
- Define function with single Pydantic object parameter
- Assume StructuredTool passes Pydantic objects to functions
- Create Pydantic objects when calling tool.func() manually
- Mix Pydantic object and kwargs patterns

## Pattern Reference

### StructuredTool Best Practice
```python
# 1. Define Pydantic schema for validation
class MyToolInput(BaseModel):
    param1: str = Field(..., description="...")
    param2: Optional[int] = Field(None, description="...")

# 2. Define function with INDIVIDUAL parameters
def my_tool_func(param1: str, param2: Optional[int] = None):
    # Implementation
    return result

# 3. Create StructuredTool
my_tool = StructuredTool(
    name="my_tool",
    description="...",
    args_schema=MyToolInput,  # For validation
    func=my_tool_func,  # Accepts individual kwargs
)

# 4. LangChain handles the rest!
# - Validates with MyToolInput
# - Unpacks as kwargs
# - Calls my_tool_func(param1="...", param2=...)
```

## Testing

All execution paths now work correctly:

1. ✅ **Serial/Sequential**: Agent calls individual tools
2. ✅ **Parallel (Tool-based)**: `invoke_parallel_genie_agents` tool
3. ✅ **Parallel (Direct)**: `invoke_genie_agents_parallel()` method

## Status
✅ **COMPLETE** - All serial and parallel execution paths have been fixed.
