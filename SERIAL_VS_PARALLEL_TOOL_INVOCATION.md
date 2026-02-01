# Serial vs Parallel Tool Invocation - CORRECTED

## TL;DR
**UPDATE**: BOTH serial and parallel tools needed fixing!

- **Serial/Individual Tools**: ❌ Were broken → ✅ Fixed
- **Parallel Tools**: ❌ Were broken → ✅ Fixed

## The Real Issue: StructuredTool Function Signatures

The error occurred because StructuredTool expects functions to accept **individual field arguments as kwargs**, not a single Pydantic object.

### Wrong Pattern (What We Had - BROKEN)
```python
class GenieToolInput(BaseModel):
    question: str
    conversation_id: Optional[str] = None

# ❌ WRONG: Function accepts single Pydantic object
def _genie_tool_call(args: GenieToolInput):
    return agent.invoke({
        "messages": [{"role": "user", "content": args.question}],
        "conversation_id": args.conversation_id,
    })

genie_tool = StructuredTool(
    args_schema=GenieToolInput,
    func=_genie_tool_call,
)

# When called: tool.func(question="...", conversation_id=...)
# Function expects: (args: GenieToolInput)
# Result: ❌ TypeError: got unexpected keyword argument 'question'
```

### Correct Pattern (Fixed)
```python
class GenieToolInput(BaseModel):
    question: str
    conversation_id: Optional[str] = None

# ✅ CORRECT: Function accepts individual kwargs
def _genie_tool_call(question: str, conversation_id: Optional[str] = None):
    return agent.invoke({
        "messages": [{"role": "user", "content": question}],
        "conversation_id": conversation_id,
    })

genie_tool = StructuredTool(
    args_schema=GenieToolInput,  # Schema for validation
    func=_genie_tool_call,  # Accepts individual kwargs
)

# When called: tool.func(question="...", conversation_id=...)
# Function expects: (question: str, conversation_id: Optional[str])
# Result: ✅ Works!
```

## Why Both Serial and Parallel Failed

### Invocation Path
```
User Query 
  → SQL Synthesis Agent (LangGraph)
    → Agent Framework decides to call tool
      → LangChain Tool Infrastructure
        → Reads tool.args_schema (GenieToolInput)
        → Validates LLM's arguments against schema
        → UNPACKS Pydantic fields as kwargs
        → Calls tool.func(question="...", conversation_id=...)  ✅
          → _genie_tool_call(question, conversation_id)  ✅ Receives correctly
```

### Code Flow (After Fix)
```python
# Individual tool definition
genie_tool = StructuredTool(
    name="Genie_Sales",
    description="...",
    args_schema=GenieToolInput,  # Pydantic schema for validation
    func=_genie_tool_call,  # Function accepts individual kwargs
)

# Agent calls the tool
sql_synthesis_agent = create_agent(model=llm, tools=[genie_tool, ...])
result = sql_synthesis_agent.invoke({"messages": [...]})

# LangChain's tool infrastructure:
# 1. Validates arguments against args_schema
# 2. Creates GenieToolInput object for validation
# 3. UNPACKS as kwargs: tool.func(**validated_input.dict())
# 4. Calls: tool.func(question="...", conversation_id=...)  ✅
```

**Key Point**: LangChain's StructuredTool validates with Pydantic BUT unpacks fields as kwargs when calling the function. The function must accept individual parameters, not a Pydantic object.

## Why Parallel Tools Needed Fixing

### The Problem (Before Fix)
```
User Query
  → invoke_parallel_genie_agents tool
    → RunnableParallel with RunnableLambda wrappers
      → RunnableLambda.invoke(GenieToolInput(...))  ❌
        → Unpacks Pydantic as kwargs
        → _genie_tool_call(question="...", conversation_id=...)  ❌ Wrong signature!
```

### Code Flow (Before Fix)
```python
# BROKEN: Wrapping in RunnableLambda and calling .invoke()
parallel_tasks[space_id] = RunnableLambda(
    lambda inp, sid=space_id: self.parallel_executors[sid].invoke(
        GenieToolInput(question=inp[sid], conversation_id=None)  ❌
    )
)
# RunnableLambda.invoke() unpacks Pydantic object as kwargs!
```

### The Fix (After)
```python
# FIXED: Call tool.func() directly
parallel_tasks[space_id] = RunnableLambda(
    lambda inp, sid=space_id, t=tool: t.func(
        GenieToolInput(question=inp[sid], conversation_id=None)  ✅
    )
)
# tool.func() receives Pydantic object as single argument!
```

**Key Point**: When we manually wrap tools in `RunnableLambda` for parallel execution, we must call `tool.func()` directly instead of `tool.invoke()` to avoid Pydantic unpacking issues.

## Summary Table

| Execution Type | Invocation Method | Status | Fix Applied |
|----------------|-------------------|---------|-------------|
| **Serial (Individual)** | Agent framework calls `tool` | ✅ Fixed | Changed function signature to accept individual kwargs |
| **Parallel (Manual)** | We wrap in `RunnableLambda` | ✅ Fixed | Changed to pass individual kwargs to `tool.func()` |

## The Fundamental Rule

**When using StructuredTool with args_schema:**

✅ **DO**: Define function with individual parameters matching schema fields
```python
class MyInput(BaseModel):
    param1: str
    param2: int

def my_func(param1: str, param2: int):  # ✅ Individual params
    ...
```

❌ **DON'T**: Define function with single Pydantic parameter
```python
class MyInput(BaseModel):
    param1: str
    param2: int

def my_func(args: MyInput):  # ❌ Single Pydantic object
    ...
```

This applies to:
- ✅ **Serial execution** (agent-called tools)
- ✅ **Parallel execution** (manually called tools)
- ✅ **Any StructuredTool** with args_schema

## Code Examples

### ✅ Fixed: StructuredTool Function Signature
```python
# Before (broken):
def _genie_tool_call(args: GenieToolInput):  ❌
    return agent.invoke({
        "messages": [{"role": "user", "content": args.question}],
        "conversation_id": args.conversation_id,
    })

# After (fixed):
def _genie_tool_call(question: str, conversation_id: Optional[str] = None):  ✅
    return agent.invoke({
        "messages": [{"role": "user", "content": question}],
        "conversation_id": conversation_id,
    })
```

### ✅ Fixed: Parallel Execution Calls
```python
# Before (broken):
parallel_tasks[sid] = RunnableLambda(
    lambda inp, t=tool: t.func(
        GenieToolInput(question=inp[sid], conversation_id=None)  ❌
    )
)

# After (fixed):
parallel_tasks[sid] = RunnableLambda(
    lambda inp, t=tool: t.func(
        question=inp[sid], conversation_id=None  ✅
    )
)
```

## Testing Confirmation

Both execution paths now work:

1. **Serial Execution** (via agent):
   ```python
   # Agent decides: "I need to call Genie_Sales tool"
   # LangChain validates and unpacks:
   # tool.func(question="...", conversation_id=...)
   # Function receives individual kwargs
   # Result: ✅ Works
   ```

2. **Parallel Execution** (manual):
   ```python
   # Our code passes individual kwargs:
   # tool.func(question="...", conversation_id=None)
   # Function receives individual kwargs
   # Result: ✅ Works
   ```

## Key Learning

**StructuredTool with args_schema** uses Pydantic for **validation only**, then **unpacks** the validated fields as kwargs to call your function. Your function signature must match the Pydantic schema fields, not accept the Pydantic object itself.
