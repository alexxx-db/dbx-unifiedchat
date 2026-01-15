# Clarification Flow Guide

## Overview

The Hybrid Super Agent now includes an improved clarification system that:
- ✅ Only asks for clarification on **truly vague** queries (lenient by default)
- ✅ Asks **at most 1 time** (no endless clarification loops)
- ✅ Provides an easy way to respond and continue the workflow
- ✅ Automatically proceeds to planning after receiving clarification

---

## How It Works

### 1. **Lenient Clarification Policy**

The ClarificationAgent is now configured to be **lenient** - it only asks for clarification when a query is truly unclear:

**✅ CLEAR Queries (proceed without clarification):**
- "How many patients are in the dataset?"
- "What is the average claim cost?"
- "Show me diabetes patients"
- "What's the cost breakdown by payer?"
- Any query with medical/business terms that can be mapped to data

**❌ UNCLEAR Queries (need clarification):**
- "How many?" (what to count is unclear)
- "Show me the data" (which data is unclear)
- "What about the thing?" (what thing is unclear)
- Queries with no context about what to analyze

### 2. **Max 1 Clarification Attempt**

The system tracks clarification attempts and enforces a maximum of 1:

```python
# State field tracks attempts
clarification_count: Optional[int]  # 0 = no clarification yet, 1 = clarified once

# Agent checks count before asking
if clarification_count >= 1:
    # Max attempts reached - proceed with best effort
    return {"question_clear": True}
```

### 3. **Clarification Response Flow**

When clarification is needed, the workflow provides options and waits for user response:

```
User Query (vague)
    ↓
[Clarification Agent]
    ├─ Analyzes query
    ├─ Determines if truly unclear
    └─ If unclear: Returns clarification options
    ↓
[Workflow Pauses]
    ├─ Sets next_agent = "end"
    ├─ Displays clarification options
    └─ Waits for user response
    ↓
[User provides clarification]
    ↓
[respond_to_clarification()]
    ├─ Incorporates user feedback
    ├─ Sets user_clarification_response
    └─ Re-enters clarification node
    ↓
[Clarification Agent]
    ├─ Detects user response
    ├─ Appends to original query
    └─ Marks as clear
    ↓
[Planning Agent]
    ↓
[SQL Synthesis]
    ↓
[SQL Execution]
    ↓
Results
```

---

## Usage Examples

### Example 1: Clear Query (No Clarification Needed)

```python
# Query is clear - proceeds directly
final_state = invoke_super_agent_hybrid(
    "How many patients are in the dataset?",
    thread_id="session_001"
)

display_results(final_state)
# Output: Shows patient count directly
```

### Example 2: Vague Query → Clarification → Results

```python
# Step 1: Try with vague query
state1 = invoke_super_agent_hybrid(
    "How many?",  # Vague!
    thread_id="session_002"
)

# Step 2: Check if clarification needed
display_results(state1)
# Output: 
#   Status: ⚠ Clarification needed
#   Reason: The query "How many?" is too vague...
#   Options:
#     1. How many patients are in the dataset?
#     2. How many medical claims were submitted?
#     3. How many procedures were performed?

# Step 3: Provide clarification
if not state1['question_clear']:
    state2 = respond_to_clarification(
        "How many patients are in the dataset?",  # User's clarification
        previous_state=state1,
        thread_id="session_002"
    )
    
    # Step 4: View results
    display_results(state2)
    # Output: Shows patient count
```

### Example 3: Choose from Suggested Options

```python
# Step 1: Vague query
state1 = invoke_super_agent_hybrid(
    "Show me the data",
    thread_id="session_003"
)

# Step 2: Agent provides options
if not state1['question_clear']:
    print("Options:", state1['clarification_options'])
    # Options:
    #   1. Show patient demographics
    #   2. Show medical claims summary
    #   3. Show diagnosis information
    
    # Step 3: Choose option 1
    state2 = respond_to_clarification(
        "Show patient demographics",  # Choosing option 1
        previous_state=state1,
        thread_id="session_003"
    )
    
    display_results(state2)
```

### Example 4: Custom Clarification

```python
# Step 1: Vague query
state1 = invoke_super_agent_hybrid(
    "What about costs?",
    thread_id="session_004"
)

# Step 2: Provide custom clarification (not from options)
if not state1['question_clear']:
    state2 = respond_to_clarification(
        "I want to see the average cost of medical claims broken down by payer type",
        previous_state=state1,
        thread_id="session_004"
    )
    
    display_results(state2)
```

---

## State Fields

New fields added to `AgentState`:

```python
class AgentState(TypedDict):
    # ... existing fields ...
    
    # Clarification tracking
    clarification_count: Optional[int]          # Number of times clarified (max 1)
    user_clarification_response: Optional[str]   # User's clarification text
```

---

## API Reference

### `invoke_super_agent_hybrid()`

Start a new query. If clarification is needed, workflow pauses.

```python
def invoke_super_agent_hybrid(
    query: str, 
    thread_id: str = "default"
) -> Dict[str, Any]:
    """
    Invoke the Hybrid Super Agent with a user query.
    
    Returns:
        Final state (may include clarification request)
    """
```

### `respond_to_clarification()`

Respond to a clarification request and continue the workflow.

```python
def respond_to_clarification(
    clarification_response: str, 
    previous_state: Dict[str, Any],
    thread_id: str = "default"
) -> Dict[str, Any]:
    """
    Respond to a clarification request and continue the workflow.
    
    Args:
        clarification_response: Your clarification/answer
        previous_state: The state from previous invoke call
        thread_id: Thread ID (must match previous call)
    
    Returns:
        Final state with execution results
    """
```

---

## Decision Logic

The ClarificationAgent uses this logic:

```python
def check_clarity(self, query: str, clarification_count: int = 0):
    # 1. Check if already clarified once
    if clarification_count >= 1:
        return {"question_clear": True}  # Max attempts reached
    
    # 2. Ask LLM to assess clarity (with lenient instructions)
    clarity_result = self.llm.invoke(clarity_prompt)
    
    # 3. Return result
    return clarity_result
```

Clarification Node logic:

```python
def clarification_node(state: AgentState):
    clarification_count = state.get("clarification_count", 0)
    
    # 1. Check if this is a user response to previous clarification
    if state.get("user_clarification_response") and clarification_count > 0:
        # Incorporate user feedback into query
        state["original_query"] += f" [User Clarification: {response}]"
        state["question_clear"] = True
        state["next_agent"] = "planning"
        return state
    
    # 2. First time - check clarity
    clarity_result = clarification_agent(query, clarification_count)
    
    # 3. If unclear, increment count and wait for user
    if not clarity_result["question_clear"]:
        state["clarification_count"] = clarification_count + 1
        state["next_agent"] = "end"  # Pause workflow
    else:
        state["next_agent"] = "planning"  # Continue
    
    return state
```

---

## Benefits

### ✅ No Endless Loops
- Maximum 1 clarification request
- After that, proceeds with best effort

### ✅ Lenient by Default
- Only asks when truly necessary
- Reduces user friction
- Better user experience

### ✅ Easy to Use
- Simple `respond_to_clarification()` function
- Clear instructions in output
- Maintains thread context

### ✅ Production Ready
- Handles edge cases
- Prevents infinite clarification loops
- Graceful degradation

---

## Testing

Test cases are included in the notebook:

1. **Test Case 1-4**: Clear queries (no clarification needed)
2. **Test Case 5**: Vague query "How many?" → Clarification flow
3. **Test Case 6**: Vague query "Show me the data" → Clarification flow

Run these to see the clarification flow in action:

```python
# Test vague query
result = invoke_super_agent_hybrid("How many?", thread_id="test_001")

# If clarification needed
if not result['question_clear']:
    result = respond_to_clarification(
        "How many patients are in the dataset?",
        previous_state=result,
        thread_id="test_001"
    )
```

---

## Production Deployment

When deployed as a Model Serving endpoint, the clarification flow works the same:

```python
from databricks_langchain import ChatDatabricks

agent = ChatDatabricks(
    endpoint="hybrid_super_agent",
    use_responses_api=True
)

# Initial query
response1 = agent.invoke(
    [{"role": "user", "content": "How many?"}],
    custom_inputs={"thread_id": "user_123"}
)

# If clarification needed, send follow-up
response2 = agent.invoke(
    [
        {"role": "user", "content": "How many?"},
        {"role": "user", "content": "Clarification: How many patients in dataset"}
    ],
    custom_inputs={"thread_id": "user_123"}
)
```

---

## Summary

| Aspect | Behavior |
|--------|----------|
| **Default Mode** | Lenient - only clarifies truly vague queries |
| **Max Attempts** | 1 clarification request maximum |
| **User Response** | Via `respond_to_clarification()` function |
| **After Clarification** | Automatically continues to planning |
| **Thread Safety** | Uses `thread_id` to maintain context |
| **Fallback** | After max attempts, proceeds with best effort |

The clarification system now provides a better user experience while preventing endless clarification loops! 🎉

---

*Last Updated: January 2026*
