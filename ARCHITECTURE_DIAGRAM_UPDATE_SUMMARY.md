# Architecture Diagram Update Summary

**Date:** February 4, 2026  
**Updated By:** AI Assistant  
**Scope:** Updated both simple and full architecture diagrams to reflect current ETL pipeline, Super_Agent_hybrid.py implementation, and highlighted the 💡 **Instructed Retriever innovation**

**Reference:** [Databricks Blog - Instructed Retriever: Unlocking System-Level Reasoning in Search Agents](https://www.databricks.com/blog/instructed-retriever-unlocking-system-level-reasoning-search-agents)

---

## What Was Updated

### 1. Architecture Diagrams (Mermaid Source Files)

#### ✅ `architecture_diagram_simple.mmd` (Simple Version)
**Changes:**
- Added **Intent Detection** node before Planning Agent
- Renamed "Thinking Agent" to **"Planning Agent"** to match code
- Added **Memory Support** indicator on Super Agent
- Restructured execution paths to show all 4 routes:
  - Single Space
  - Multi + Join (Table Route)
  - Multi + Join (Genie Route)  
  - Multi - No Join (Verbal Merge)
- Added **Summarize Agent** as final step before returning to user
- Enhanced **ETL Pipeline** section with build order (1→2→3):
  1. Export Genie Spaces
  2. Enrich Table Metadata
  3. Build VS Index
- Added **Lakebase** as memory data store
- Updated color scheme with ETL class (purple) for pipeline components

#### ✅ `architecture_diagram.mmd` (Full Version)
**Major Changes:**
- Added **Memory Integration** with Lakebase (checkpoints + user memories)
- Added **Intent Detection & Clarification Flow**:
  - Intent Type classification
  - Meta Question handling
  - Clarification Node
- Restructured **Planning Agent** to show:
  - Vector Search Tool
  - Execution Plan Creation
  - Decision routing
- Added all **specialized agents** from Super_Agent_hybrid.py:
  - SuperAgentHybridResponsesAgent (with memory)
  - Planning Agent
  - SQL Synthesis Table Agent (with UC Functions)
  - SQL Synthesis Genie Agent
  - SQL Execution Agent
  - Result Summarize Agent
- Added **UC Function Toolkit** detail:
  - get_space_summary
  - get_table_overview
  - get_column_detail
  - get_space_details
- Enhanced **ETL Pipeline** with 3 detailed subgraphs:
  - Notebook 1: Export Genie Spaces (00_Export_Genie_Spaces.py)
  - Notebook 2: Enrich Table Metadata (02_Table_MetaInfo_Enrichment.py)
  - Notebook 3: Build Vector Search Index (04_VS_Enriched_Genie_Spaces.py)
- Added **Memory class** (teal color) for Lakebase components
- Updated all data flows to reflect actual implementation

### 2. Rendered Diagram Files (SVG + PDF)

#### ✅ `architecture_diagram_simple.svg` (45KB) + `architecture_diagram_simple.pdf` (191KB)
- Generated from updated simple.mmd
- Neutral theme with transparent background
- Optimized for embedding in documentation
- PDF version for high-quality printing and presentations

#### ✅ `architecture_diagram.svg` (121KB) + `architecture_diagram.pdf` (232KB)
- Generated from updated full diagram
- Larger canvas (3000x2500) for detailed view
- Shows all agents, data flows, and ETL pipeline
- **Highlights the Instructed Retriever innovation** with special callouts
- High-resolution for presentations
- PDF version for professional distribution

### 3. Documentation

#### ✅ `ARCHITECTURE_DIAGRAM.md`
**Updated Sections:**

1. **Overview** - Updated to reflect 4 main components including Memory System
2. **Architecture Components** - Detailed all 8 agents from Super_Agent_hybrid.py
3. **Decision Points** - Updated to show Intent Type classification and Execution Route
4. **Execution Paths** - Detailed explanation of all 4 paths with code examples
5. **ETL Pipeline** - Complete 3-notebook workflow with:
   - Build order dependencies
   - Configuration parameters
   - Purpose and features of each notebook
6. **Data Stores** - Added Lakebase with short-term and long-term memory
7. **Integration** - Added Lakebase, UC Functions, SQL Warehouse
8. **Current Features** - Replaced "Future Components" with implemented features
9. **Query Flow Example** - Updated with actual agent flow including intent detection
10. **Build and Deployment Order** - Added step-by-step guide
11. **Key Design Decisions** - New section explaining architecture choices
12. **Color Legend** - Updated with new color classes including Memory (teal)

---

## Key Improvements

### 1. 💡 Innovation Highlight: Instructed Retriever
✅ **Multi-step Instructed Retrieval** marked as key innovation in diagrams  
✅ UC Function Toolkit shown as implementation of [Databricks Instructed Retriever architecture](https://www.databricks.com/blog/instructed-retriever-unlocking-system-level-reasoning-search-agents)  
✅ Hierarchical metadata retrieval flow visualized (summary → table → column → details)  
✅ System specifications propagation illustrated  
✅ Performance improvements documented (35-50% recall, 70%+ response quality)  
✅ Detailed section in documentation explaining the innovation  

### 2. Accurate Representation
✅ Diagrams now match the actual implementation in `Super_Agent_hybrid.py`  
✅ All agent classes properly represented  
✅ ETL pipeline reflects actual notebooks (00, 02, 04)  
✅ Memory system integration shown

### 3. Better Clarity
✅ Simple diagram focuses on high-level flow + ETL  
✅ Full diagram shows all technical details  
✅ ETL pipeline shows build order (1→2→3)  
✅ All 4 execution paths clearly distinguished  
✅ Innovation callouts with emoji markers (💡)

### 4. Enhanced Documentation
✅ Detailed ETL notebook descriptions  
✅ Configuration parameters documented  
✅ Build and deployment order provided  
✅ Design decisions explained  
✅ Query flow example updated with current flow  
✅ **New section**: "Key Innovation: Multi-step Instructed Retrieval"  
✅ Performance comparison tables added  
✅ Implementation details provided

### 5. Memory System Integration
✅ Lakebase shown as central memory store  
✅ Short-term (checkpoints) and long-term (user memories) distinction  
✅ Memory class color (teal) for visual clarity

### 6. Multiple Export Formats
✅ SVG files for web and documentation  
✅ **PDF files for high-quality printing and presentations**  
✅ Mermaid source files for easy editing

---

## Files Modified and Created

### Mermaid Source Files
- ✅ `architecture_diagram_simple.mmd` - Simple version updated with innovation markers
- ✅ `architecture_diagram.mmd` - Full version updated with detailed UC Functions callout

### Generated SVG Files
- ✅ `architecture_diagram_simple.svg` - Regenerated (45KB)
- ✅ `architecture_diagram.svg` - Regenerated (121KB) with innovation highlights

### Generated PDF Files (NEW! 📄)
- ✅ `architecture_diagram_simple.pdf` - High-quality print version (191KB)
- ✅ `architecture_diagram.pdf` - High-quality print version (232KB)

### Documentation
- ✅ `ARCHITECTURE_DIAGRAM.md` - Comprehensive updates including:
  - New section: "Key Innovation: Multi-step Instructed Retrieval"
  - Performance comparison tables
  - Implementation details with code examples
  - Download links for SVG and PDF formats
  - Reference to Databricks blog post

### New Files
- ✅ `ARCHITECTURE_DIAGRAM_UPDATE_SUMMARY.md` - This file

---

## ETL Pipeline Details (From Notebooks)

### Build Order: 1 → 2 → 3

#### 1. Export Genie Spaces (`00_Export_Genie_Spaces.py`)
**Purpose:** Export Genie space metadata to Unity Catalog Volume

**Key Features:**
- Fetches space.json via Databricks Genie API
- Saves to `/Volumes/{catalog}/{schema}/{volume}/genie_exports/`
- Configurable via `GENIE_SPACE_IDS` environment variable

**Configuration:**
```python
DATABRICKS_HOST
DATABRICKS_TOKEN
CATALOG_NAME=yyang
SCHEMA_NAME=multi_agent_genie
VOLUME_NAME=volume
GENIE_SPACE_IDS=space_id_1,space_id_2,...
```

#### 2. Enrich Table Metadata (`02_Table_MetaInfo_Enrichment.py`)
**Purpose:** Enrich Genie metadata with table details and create multi-level chunks

**Key Features:**
- Samples column values from Delta tables
- Builds value frequency dictionaries
- Creates 3 chunk types:
  - `space_summary` - High-level space info
  - `table_overview` - Table schemas
  - `column_detail` - Column metadata with samples
- Enriches with table metadata from `DESCRIBE EXTENDED`
- Saves to `enriched_genie_docs_chunks` Delta table

**Configuration:**
```python
catalog_name=yyang
schema_name=multi_agent_genie
genie_exports_volume=yyang.multi_agent_genie.volume
enriched_docs_table=yyang.multi_agent_genie.enriched_genie_docs
sample_size=20  # Number of column value samples
max_unique_values=20  # Max unique values in dictionary
```

#### 3. Build Vector Search Index (`04_VS_Enriched_Genie_Spaces.py`)
**Purpose:** Create vector search index for semantic search

**Key Features:**
- Creates VS endpoint if not exists
- Enables Change Data Feed (CDC)
- Creates Delta Sync index:
  - Primary key: `chunk_id`
  - Embedding source: `searchable_content`
  - Embedding model: `databricks-gte-large-en`
- Filterable metadata: chunk_type, table_name, column_name

**Configuration:**
```python
catalog_name=yyang
schema_name=multi_agent_genie
source_table=enriched_genie_docs_chunks
vs_endpoint_name=genie_multi_agent_vs
embedding_model=databricks-gte-large-en
pipeline_type=TRIGGERED  # or CONTINUOUS
```

---

## Agent Architecture (From Super_Agent_hybrid.py)

### Main Agents

1. **SuperAgentHybridResponsesAgent**
   - ResponsesAgent wrapper
   - Short-term memory: Lakebase CheckpointSaver
   - Long-term memory: Lakebase DatabricksStore with embeddings
   - Streaming support with custom events

2. **Planning Agent** (`PlanningAgent`)
   - Vector search integration
   - Query breakdown and sub-task analysis
   - Execution plan creation with routing strategy

3. **SQL Synthesis Table Agent** (`SQLSynthesisTableAgent`)
   - Fast path using UC function tools
   - Hierarchical metadata retrieval
   - Parallel UC function calls

4. **SQL Synthesis Genie Agent** (`SQLSynthesisGenieAgent`)
   - Accurate path combining Genie agent results
   - SQL merging and joining

5. **SQL Execution Agent** (`SQLExecutionAgent`)
   - SQL Warehouse integration
   - Query validation and execution
   - Result formatting (dict/markdown/dataframe)

6. **Result Summarize Agent** (`ResultSummarizeAgent`)
   - Natural language result formatting
   - Streaming response generation

### Decision Flow

```
User Query
  ↓
Intent Detection (new_question | refinement | meta_question | unclear)
  ↓
[If meta_question] → Answer directly
[If unclear] → Request clarification
[If clear] → Planning Agent
  ↓
Vector Search (find relevant spaces)
  ↓
Create Execution Plan
  ↓
Routing Decision:
  - Single Space → Call Genie Agent
  - Multi + Join (Table Route) → SQL Synthesis Table Agent
  - Multi + Join (Genie Route) → SQL Synthesis Genie Agent  
  - Multi - No Join → Verbal Merge
  ↓
SQL Execution Agent
  ↓
Result Summarize Agent
  ↓
Return to User (thinking_result, sql_result, answer_result)
```

---

## Memory System Architecture

### Short-Term Memory (Checkpoints)
**Storage:** Lakebase checkpoints table  
**Scope:** Per thread_id (conversation)  
**Purpose:** Multi-turn conversation state  
**Implementation:** LangGraph CheckpointSaver  

**Stored Data:**
- Conversation messages
- Agent state (current_turn, turn_history, intent_metadata)
- Planning results
- SQL queries and results

### Long-Term Memory (User Memories)
**Storage:** Lakebase store table with vector embeddings  
**Scope:** Per user_id (across conversations)  
**Purpose:** User preferences and facts  
**Implementation:** DatabricksStore with semantic search  

**Features:**
- `get_user_memory(query)` - Semantic search
- `save_user_memory(key, data)` - Store preference
- `delete_user_memory(key)` - Remove preference

---

## Color Scheme

### Diagram Color Classes

- **Blue (#4A90E2)** - `agentClass` - All agent components
- **Green (#50C878)** - `dataClass` - Data stores (Delta tables, VS index)
- **Orange (#F5A623)** - `processClass` - Processing nodes (intent detection, search, execution)
- **Red (#E94B3C)** - `decisionClass` - Decision points (intent type, routing)
- **Purple (#9B59B6)** - `pipelineClass` - ETL pipeline components (export, enrich, index)
- **Teal (#16A085)** - `memoryClass` - Memory system (Lakebase)

---

## Usage

### Viewing the Diagrams

1. **In GitHub:** Diagrams render automatically in Markdown
2. **In Documentation:** SVG files embedded in ARCHITECTURE_DIAGRAM.md
3. **In Presentations:** Use high-resolution SVG files
4. **In Editors:** Open .mmd files in Mermaid Live Editor

### Updating the Diagrams

1. Edit `.mmd` files with any text editor
2. Regenerate SVG files:
   ```bash
   cd /Users/yang.yang/CursorProjects/KUMC_POC_hlsfieldtemp
   
   # Simple diagram
   npx -p @mermaid-js/mermaid-cli mmdc \
     -i architecture_diagram_simple.mmd \
     -o architecture_diagram_simple.svg \
     -t neutral -b transparent
   
   # Full diagram
   npx -p @mermaid-js/mermaid-cli mmdc \
     -i architecture_diagram.mmd \
     -o architecture_diagram.svg \
     -t neutral -b transparent \
     -w 3000 -H 2500
   ```
3. Update ARCHITECTURE_DIAGRAM.md if needed

---

## Next Steps

### For New Team Members
1. Read `ARCHITECTURE_DIAGRAM.md` for overview
2. Review simple diagram for high-level understanding
3. Study full diagram for technical details
4. Follow ETL pipeline build order

### For Deployment
1. Run ETL pipeline (notebooks 00 → 02 → 04)
2. Configure `.env` with all settings
3. Test with `Super_Agent_hybrid.py`
4. Deploy to MLflow Model Serving

### For Future Updates
- Update diagrams when adding new agents
- Update ETL pipeline section when adding notebooks
- Keep color scheme consistent
- Regenerate SVG files after changes

---

---

## 💡 Instructed Retriever Innovation Details

### What It Is
The **Instructed Retriever** is a novel retrieval architecture from Databricks that addresses fundamental limitations of traditional RAG by enabling system-level reasoning in search agents.

### Key Capabilities

1. **System Specifications Propagation**
   - User instructions, execution plans, and index schemas flow through all stages
   - Not just the user query, but complete context for instruction-following

2. **Hierarchical Metadata Retrieval**
   - Minimal sufficiency principle: Start lightweight, add detail only if needed
   - UC functions implement staged retrieval: summary → table → column → details
   - Parallel execution for speed

3. **Instruction-Following Query Generation**
   - Translates natural language to precise SQL filters
   - Schema-aware: Only uses fields that exist in the index
   - Handles complex constraints (inclusion, exclusion, recency)

4. **Metadata Reasoning**
   - Query decomposition into multiple structured searches
   - Contextual relevance beyond text similarity
   - True understanding of user intent in context

### Performance Improvements (Databricks Research)

| Metric | Improvement vs RAG |
|--------|-------------------|
| Retrieval Recall | **+35-50%** |
| Response Quality (Enterprise QA) | **+70%+** |
| vs RAG + Rerank | **+15%** |
| Multi-step Agent (vs RAG tool) | **+30%** |
| Time to Completion | **-8%** (faster) |

### Our Implementation

**Location:** `SQLSynthesisTableAgent` in `Super_Agent_hybrid.py`

**UC Functions:**
```python
# Hierarchical metadata retrieval
get_space_summary(space_ids_json)      # High-level (first attempt)
get_table_overview(space_ids_json)     # Table schemas (if needed)
get_column_detail(space_ids_json)      # Column details (specific columns)
get_space_details(space_ids_json)      # Complete (last resort)
```

**Data Source:** `enriched_genie_docs_chunks` Delta table with multi-level chunks

**Features:**
- Instruction-aware LLM system prompt
- Parallel UC function calls (reduces latency)
- Schema-aware query validation
- Offline RL for small model optimization

### Why This Matters

1. **Enterprise-Ready**: Handles complex, multi-part instructions
2. **Cost-Effective**: Small models achieve frontier performance
3. **Low Latency**: Single-step execution with intelligent fetching
4. **Accurate**: Schema awareness reduces hallucinations
5. **Scalable**: Works across heterogeneous knowledge sources

---

## Summary

✅ **All diagrams updated** to reflect current implementation  
✅ **💡 Innovation highlighted**: Multi-step Instructed Retrieval with UC Functions  
✅ **ETL pipeline documented** with 3-notebook workflow  
✅ **Memory system integrated** with Lakebase  
✅ **All agents represented** from Super_Agent_hybrid.py  
✅ **SVG files regenerated** for high-quality viewing  
✅ **PDF files created** for printing and presentations (NEW!)  
✅ **Documentation enhanced** with detailed innovation section and performance data  
✅ **Referenced Databricks research** on Instructed Retriever architecture  

The architecture diagrams now accurately represent the current KUMC POC Multi-Agent System with complete ETL pipeline, memory support, and the innovative Instructed Retriever implementation via UC Functions.
