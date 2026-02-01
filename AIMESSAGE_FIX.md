# AIMessage Content Extraction Fix

## Issue

The parallel execution was succeeding but failing when extracting SQL from the results with error:
```
'AIMessage' object has no attribute 'get'
```

## Root Cause

The Genie agent returns results in this structure:
```python
{
    'messages': [
        AIMessage(content='...', name='query_reasoning', ...),
        AIMessage(content='SELECT ...', name='query_sql', ...),
        AIMessage(content='...', name='query_result', ...)
    ],
    'conversation_id': '...'
}
```

The old code tried to use `.get()` on an `AIMessage` object:
```python
# ❌ WRONG - AIMessage is an object, not a dict
sql = result.get("messages", [{}])[-1].get("content", "")
```

## Solution

Changed to properly access the `content` attribute of `AIMessage` objects:

```python
# ✅ CORRECT - Access content as an attribute
sql_fragments = {}
for space_id, result in parallel_results.items():
    sql = ""
    if isinstance(result, dict) and "messages" in result:
        messages = result.get("messages", [])
        # Look for message with name='query_sql' (contains the SQL)
        for msg in messages:
            if hasattr(msg, 'name') and msg.name == 'query_sql':
                sql = msg.content if hasattr(msg, 'content') else str(msg)
                break
        # Fallback to last message if no query_sql found
        if not sql and messages:
            last_msg = messages[-1]
            sql = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
    else:
        sql = str(result)
    sql_fragments[space_id] = sql
```

## Benefits

1. **Smart Extraction**: Looks for the message with `name='query_sql'` which contains the actual SQL query
2. **Robust Fallback**: Falls back to last message if no `query_sql` found
3. **Safe Access**: Uses `hasattr()` to safely check for attributes
4. **Proper Typing**: Accesses `.content` as an attribute, not a dict key

## Files Modified

1. ✅ `/Notebooks/Super_Agent_hybrid.py` - Lines ~1520-1536
2. ✅ `/Notebooks/Super_Agent_hybrid_local_dev.py` - Lines ~1218-1234

## Testing

The fix enables proper extraction of SQL from parallel Genie agent results:

**Input (from parallel execution):**
```python
{
  'space_id': {
    'messages': [
      AIMessage(content='...', name='query_reasoning'),
      AIMessage(content='SELECT ...', name='query_sql'),  # ← Extract this!
      AIMessage(content='Results: ...', name='query_result')
    ]
  }
}
```

**Output (sql_fragments):**
```python
{
  'space_id': 'SELECT ...'  # Successfully extracted SQL
}
```

## Status

✅ **FIXED** - Both main and local dev files updated
