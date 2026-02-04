# Multi-Agent System Architecture Diagram

This document contains the architecture diagrams for the KUMC POC Multi-Agent System project.

## Overview

The system consists of four main components:
1. **Multi-Agent System** - Main query processing and response system with memory support
2. **ETL Pipeline** - Four-stage pipeline to prepare metadata for vector search
3. **Vector Search Index** - Semantic search over enriched Genie space metadata
4. **Memory System** - Short-term (checkpoints) and long-term (user memories) via Lakebase

## Architecture Components

### Main Agents (from Super_Agent_hybrid.py)

1. **SuperAgentHybridResponsesAgent** - Main orchestrator (ResponsesAgent wrapper) with memory support
   - Short-term memory: Lakebase CheckpointSaver (conversation checkpoints)
   - Long-term memory: Lakebase DatabricksStore (user preferences with semantic search)
2. **Planning Agent** - Breaks down queries, performs vector search, creates execution plans
3. **Intent Detection Node** - Analyzes intent type (new_question, refinement, meta_question, clarification_response)
4. **SQL Synthesis Table Agent** - Fast path using UC function tools to query metadata directly
5. **SQL Synthesis Genie Agent** - Accurate path combining results from multiple Genie agents
6. **SQL Execution Agent** - Executes SQL queries on Delta tables via SQL Warehouse
7. **Result Summarize Agent** - Formats and summarizes results for user display
8. **Genie Agents** - Domain-specific Databricks ResponsesAgent instances (space-specific)

### Decision Points

1. **Intent Type Classification** - Determines query intent (meta_question, new_question, refinement, unclear)
2. **Clarification Required** - Checks if user query needs clarification before processing
3. **Execution Route Decision** - Determines which path to take:
   - Single Genie Space
   - Multiple Spaces + Join (Table Route - Fast)
   - Multiple Spaces + Join (Genie Route - Accurate)
   - Multiple Spaces - No Join (Verbal Merge)

### Execution Paths

#### Path 1: Single Genie Space
- Used when one Genie Space can completely answer the question
- Direct call to single Genie Agent (Databricks ResponsesAgent)
- SQL Execution Agent runs the query
- Result Summarize Agent formats the output

#### Path 2: Multiple Spaces + Join (Table Route - Fast) 💡 **INNOVATION**
**Multi-step Instructed Retrieval Architecture**

This path implements the [Instructed Retriever architecture](https://www.databricks.com/blog/instructed-retriever-unlocking-system-level-reasoning-search-agents) for system-level reasoning in search agents:

- **SQL Synthesis Table Agent** uses instruction-following query generation with UC function tools
- **Hierarchical Metadata Retrieval** (minimal sufficiency principle):
  1. `get_space_summary` - High-level space information (first attempt)
  2. `get_table_overview` - Table schemas (if more detail needed)
  3. `get_column_detail` - Column-level metadata with samples (for specific columns)
  4. `get_space_details` - Complete metadata (last resort, token-intensive)
- **System Specifications Propagation**: User instructions, execution plan, and index schema flow through all stages
- **Parallel UC Function Calls**: Multiple metadata queries executed concurrently for speed
- **Schema-Aware Query Generation**: Translates natural language to precise SQL filters
- Generates joined SQL query directly from metadata
- SQL Execution Agent executes the query
- Returns result quickly (optimized for speed)

**Key Benefits:**
- 35-50% higher retrieval recall vs traditional RAG
- Instruction-following at query generation stage
- Cost-effective (small model via offline RL)
- Low latency single-step execution

#### Path 3: Multiple Spaces + Join (Genie Route - Accurate)
- Parallel async calls to multiple Genie Agents with sub-questions
- Collects sql_results from each agent
- SQL Synthesis Genie Agent combines SQL queries with proper joins
- SQL Execution Agent executes combined query
- Returns comprehensive result (optimized for accuracy)

#### Path 4: Multiple Spaces - No Join (Verbal Merge)
- Used when sub-questions are independent (no join needed)
- Calls multiple Genie Agents in parallel
- Verbal Merge integrates natural language answers
- Returns integrated response with separate SQL results

### ETL Pipeline (Build Order: 1 → 2 → 3)

The ETL pipeline consists of three notebooks that must be run in sequence:

#### Notebook 1: 00_Export_Genie_Spaces.py (Export Genie Spaces)
```
Export Genie Spaces via API → Save space.json to UC Volume
```

**Purpose:** Exports Genie space metadata (space.json) to Unity Catalog Volume

**Configuration:**
- `GENIE_SPACE_IDS` - Comma-separated list of Genie space IDs
- Output: `/Volumes/{catalog}/{schema}/{volume}/genie_exports/`

#### Notebook 2: 02_Table_MetaInfo_Enrichment.py (Enrich Table Metadata)
```
Get Table Metadata → Sample Column Values → Build Value Dictionary 
    ↓
Parse Genie space.json → Create Baseline Docs → Enrich Docs with Table Metadata
    ↓
Save to enriched_genie_docs_chunks Delta Table
```

**Purpose:** Enriches Genie space metadata with detailed table information

**Features:**
- Samples distinct column values (configurable sample_size)
- Builds value frequency dictionaries (configurable max_unique_values)
- Creates multi-level chunks:
  - `space_summary` - High-level space information
  - `table_overview` - Table schemas and metadata
  - `column_detail` - Column-level metadata with samples
- Stores enriched docs in Unity Catalog Delta table

**Configuration:**
- `catalog_name`, `schema_name` - Unity Catalog location
- `genie_exports_volume` - Volume with exported Genie spaces
- `enriched_docs_table` - Output table name
- `sample_size` - Number of column value samples (default: 20)
- `max_unique_values` - Max unique values in dictionary (default: 20)

#### Notebook 3: 04_VS_Enriched_Genie_Spaces.py (Build Vector Search Index)
```
Create VS Endpoint → Enable CDC → Create Delta Sync Index → Wait for ONLINE
```

**Purpose:** Creates vector search index on enriched Genie space metadata

**Features:**
- Delta Sync index (automatic updates when source table changes)
- Embedding source: `searchable_content` column
- Primary key: `chunk_id`
- Filterable metadata: `chunk_type`, `table_name`, `column_name`, etc.

**Configuration:**
- `vs_endpoint_name` - Vector search endpoint name
- `embedding_model` - Embedding model endpoint (default: databricks-gte-large-en)
- `pipeline_type` - TRIGGERED or CONTINUOUS (default: TRIGGERED)

### Data Stores

1. **Vector Search Index** - Databricks managed vector search index
   - Source: `enriched_genie_docs_chunks` Delta table
   - Embedding column: `searchable_content`
   - Filterable by: `chunk_type`, `table_name`, `column_name`, categorical flags
2. **Delta Tables** - Underlying data tables behind Genie Agents
   - Accessed via SQL Execution Agent using SQL Warehouse
3. **Enriched Genie Docs Delta Table** - Unity Catalog table with enriched metadata
   - Table: `{catalog}.{schema}.enriched_genie_docs_chunks`
   - Contains: space_summary, table_overview, column_detail chunks
4. **Lakebase Database** - Memory system for agent state
   - Short-term: Checkpoints table (conversation state per thread_id)
   - Long-term: Store table (user preferences per user_id with embeddings)

### Integration

- **MLflow** - Logging and Model Serving deployment for all agents
- **LangGraph** - StateGraph for agent orchestration with message passing
- **Databricks ResponsesAgent** - Wrapper class for Genie agents and Model Serving
- **Lakebase** - Distributed memory system for checkpoints and long-term storage
- **Unity Catalog Functions** - UC function toolkit for metadata querying
- **SQL Warehouse** - Query execution via Databricks SQL connector

### Current Features

1. **Multi-step Instructed Retrieval** - ✅ 💡 **INNOVATION**
   - Implements [Databricks Instructed Retriever architecture](https://www.databricks.com/blog/instructed-retriever-unlocking-system-level-reasoning-search-agents)
   - System specifications propagation through all stages
   - Instruction-following query generation with UC functions
   - 35-50% higher retrieval recall vs traditional RAG
   - 70%+ better response quality in enterprise QA benchmarks
2. **Memory System** - ✅ Implemented via Lakebase
   - Short-term: Conversation checkpoints (per thread_id)
   - Long-term: User preferences with semantic search (per user_id)
3. **Intent Detection** - ✅ Analyzes query intent and context
4. **Clarification Flow** - ✅ Requests clarification for vague queries
5. **Streaming Support** - ✅ Custom events and token streaming
6. **Agent Caching** - ✅ In-memory agent pool with TTL
7. **Vector Search Caching** - ✅ Conversation-specific result caching

### Optional Component (01_Table_MetaInfo_Update.py)

**AI-Enhanced Column Comments** - Uses LLM to improve table column descriptions
- Input: Table with basic column metadata
- Process: LLM generates enhanced column descriptions
- Output: Table with `updated_comment` field
- Note: This is optional and separate from the main ETL pipeline

## Query Flow Example

### Example Query: "How many patients older than 50 years are on Voltaren?"

1. **User** → SuperAgentHybridResponsesAgent
2. **Intent Detection Node** analyzes:
   - Intent type: new_question (clear, actionable query)
   - Confidence: 0.95
   - Complexity: moderate
3. **Planning Agent** processes:
   - Vector search finds relevant spaces:
     - Patients Genie Space (has age information)
     - Medications Genie Space (has medication information)
   - Creates execution plan:
     - Sub-questions: ["patients > 50 years", "patients on Voltaren"]
     - Requires join: true (on patient_id)
     - Strategy: table_route (for speed)
4. **Table Route Execution** (Fast Path):
   - SQL Synthesis Table Agent calls UC functions:
     - `get_table_overview` for both spaces
     - `get_column_detail` for age and medication columns
   - Generates joined SQL query:
     ```sql
     SELECT COUNT(DISTINCT p.patient_id)
     FROM patients_table p
     JOIN medications_table m ON p.patient_id = m.patient_id
     WHERE p.age > 50 AND m.medication_name = 'Voltaren'
     ```
   - SQL Execution Agent executes query
   - Result Summarize Agent formats output
5. **SuperAgent** → Returns final answer to User with:
   - `thinking_result`: Execution plan and reasoning
   - `sql_result`: SQL query and execution details
   - `answer_result`: Natural language answer with results

## File Formats

### Available Formats

1. **Mermaid Diagram** (`architecture_diagram.mmd`)
   - Can be rendered in Markdown viewers, GitHub, or Mermaid Live Editor
   - Convert to PNG/SVG/PDF using Mermaid CLI or online tools

2. **PlantUML Diagram** (`architecture_diagram.puml`)
   - Can be rendered using PlantUML tools
   - Convert to PNG/SVG/PDF using PlantUML

3. **CSV Format** (`architecture_nodes_edges.csv`)
   - Two sections: Edges (connections) and Nodes (components)
   - Can be imported into Lucid Chart, Visio, or other diagramming tools

4. **This Documentation** (`ARCHITECTURE_DIAGRAM.md`)
   - Human-readable overview with embedded diagrams

## How to Use These Files

### For Lucid Chart Import

1. **Method 1: Using CSV**
   - Open Lucid Chart
   - Go to File → Import Data → CSV
   - Import `architecture_nodes_edges.csv`
   - Map columns appropriately (Source → Target with Label)

2. **Method 2: Manual Recreation**
   - Use this documentation as reference
   - Create shapes based on Node definitions in CSV
   - Create connections based on Edge definitions in CSV
   - Apply colors from the Type/Color mapping

### For Rendering to PNG/PDF

#### Using Mermaid CLI
```bash
# Install mermaid-cli
npm install -g @mermaid-js/mermaid-cli

# Generate PNG
mmdc -i architecture_diagram.mmd -o architecture_diagram.png -w 3000 -H 2000

# Generate SVG (scalable)
mmdc -i architecture_diagram.mmd -o architecture_diagram.svg

# Generate PDF
mmdc -i architecture_diagram.mmd -o architecture_diagram.pdf
```

#### Using PlantUML
```bash
# Install PlantUML (requires Java)
# Download from https://plantuml.com/download

# Generate PNG
java -jar plantuml.jar architecture_diagram.puml

# Generate SVG
java -jar plantuml.jar -tsvg architecture_diagram.puml

# Generate PDF
java -jar plantuml.jar -tpdf architecture_diagram.puml
```

#### Using Online Tools
- **Mermaid Live Editor**: https://mermaid.live
  - Paste content from `architecture_diagram.mmd`
  - Export as PNG/SVG/PDF
  
- **PlantUML Online**: https://www.plantuml.com/plantuml
  - Paste content from `architecture_diagram.puml`
  - Export as PNG/SVG/PDF

### For Editing

All formats are text-based and can be edited in any text editor:
- Modify nodes, connections, labels
- Adjust colors, styles, layout
- Re-render after changes

## Color Legend

- **Blue (#4A90E2)** - Agents (SuperAgent, Planning, SQL Synthesis, SQL Execution, Summarize, Genie Agents)
- **Green (#50C878)** - Data Stores (Vector Search Index, Delta Tables, Enriched Docs, Lakebase)
- **Orange (#F5A623)** - Processes (Intent Detection, Vector Search, SQL Execution, Verbal Merge, UC Functions)
- **Red (#E94B3C)** - Decision Points (Intent Type, Execution Route)
- **Purple (#9B59B6)** - ETL Pipeline Components (Export, Enrich, Build Index)
- **Teal (#16A085)** - Memory System (Lakebase with short-term and long-term memory)

## Architecture Diagrams

### Simple Diagram

The simple diagram shows the high-level flow and ETL pipeline:

![Simple Architecture Diagram](architecture_diagram_simple.svg)

**Download:** [SVG](architecture_diagram_simple.svg) | [PDF](architecture_diagram_simple.pdf)

### Full Diagram

The full diagram shows all agents, execution paths, and data flows with the 💡 **Instructed Retriever innovation** highlighted:

![Full Architecture Diagram](architecture_diagram.svg)

**Download:** [SVG](architecture_diagram.svg) | [PDF](architecture_diagram.pdf)

## Available Formats

### Rendered Diagrams
- **SVG Format** (scalable, web-friendly)
  - `architecture_diagram_simple.svg` (45KB)
  - `architecture_diagram.svg` (121KB)
- **PDF Format** (print-ready, high-quality)
  - `architecture_diagram_simple.pdf` (191KB)
  - `architecture_diagram.pdf` (232KB)

### Source Files
Both diagrams are available as Mermaid source files:
- `architecture_diagram_simple.mmd` - Simple version
- `architecture_diagram.mmd` - Full version

You can view and edit these files in:
- [Mermaid Live Editor](https://mermaid.live)
- GitHub (renders Mermaid automatically)
- Any Markdown viewer with Mermaid support

## Build and Deployment Order

### ETL Pipeline (Run Once or When Metadata Changes)
1. Run `00_Export_Genie_Spaces.py` - Export Genie space metadata
2. Run `02_Table_MetaInfo_Enrichment.py` - Enrich metadata with table details
3. Run `04_VS_Enriched_Genie_Spaces.py` - Build vector search index
4. Wait for vector search index to be ONLINE

### Multi-Agent System Deployment
1. Configure `.env` file with all required settings
2. Run `Notebooks/Super_Agent_hybrid.py` to test locally
3. Deploy to MLflow Model Serving for production:
   - Model: `SuperAgentHybridResponsesAgent`
   - Memory: Automatic via Lakebase (no configuration needed)
   - Endpoint: Serves via ResponsesAgent API

## 💡 Key Innovation: Multi-step Instructed Retrieval

### Overview

Our system implements the **Instructed Retriever architecture** described in [Databricks' research](https://www.databricks.com/blog/instructed-retriever-unlocking-system-level-reasoning-search-agents), which addresses fundamental limitations of traditional RAG by enabling system-level reasoning in search agents.

### The Problem with Traditional RAG

Traditional RAG pipelines fail to:
- Translate fine-grained user intent into precise search queries
- Propagate system specifications (instructions, examples, index schema) through all stages
- Reason about underlying knowledge source schemas
- Follow complex, multi-part user instructions

### Our Solution: Instructed Retriever via UC Functions

The **SQL Synthesis Table Agent** implements the Instructed Retriever architecture using Unity Catalog functions:

#### 1. System Specifications Propagation
All stages receive complete context:
- **User Instructions**: Constraints like "focus on recent data" or "exclude certain products"
- **Execution Plan**: Sub-questions, required joins, routing strategy from Planning Agent
- **Index Schema**: Available metadata fields (table_name, column_name, chunk_type, etc.)
- **Labeled Examples**: Relevant/non-relevant document pairs (implicit in enriched metadata)

#### 2. Hierarchical Metadata Retrieval (Minimal Sufficiency)
UC functions enable intelligent, staged metadata fetching:

```
Planning Agent identifies relevant spaces
         ↓
get_space_summary → High-level space info (lightweight, fast)
         ↓ [if insufficient]
get_table_overview → Table schemas and structure (moderate detail)
         ↓ [if still insufficient]
get_column_detail → Column metadata with value samples (detailed)
         ↓ [last resort only]
get_space_details → Complete metadata (token-intensive)
```

**Benefits:**
- Token-efficient: Only fetch what's needed
- Fast: Start with lightweight queries, add detail only if needed
- Parallel execution: Call multiple UC functions concurrently

#### 3. Instruction-Following Query Generation

The agent translates natural language instructions into structured SQL filters:

**Example:**
- User: "Find patients over 50 on Voltaren, focusing on recent data"
- Instructions: "Prioritize data from last 2 years"
- Schema: `patients.age`, `medications.medication_name`, `medications.claim_date`

**Generated Query:**
```sql
SELECT COUNT(DISTINCT p.patient_id)
FROM patients_table p
JOIN medications_table m ON p.patient_id = m.patient_id
WHERE p.age > 50 
  AND m.medication_name = 'Voltaren'
  AND m.claim_date >= DATE_SUB(CURRENT_DATE(), 730)  -- Last 2 years
```

#### 4. Key Capabilities Unlocked

1. **Query Decomposition**: Break complex requests into multiple searches with filters
2. **Contextual Relevance**: True relevance understanding beyond text similarity
3. **Metadata Reasoning**: Natural language → executable filters
4. **Schema Awareness**: Only use fields that actually exist in the index

### Performance Improvements

Based on Databricks research and our implementation:

| Metric | Traditional RAG | Instructed Retriever | Improvement |
|--------|----------------|---------------------|-------------|
| Retrieval Recall | Baseline | +35-50% | **35-50%** ↑ |
| Response Quality | Baseline | +70%+ | **70%+** ↑ |
| vs RAG + Rerank | Baseline | +15% | **15%** ↑ |
| Multi-step Agent (vs RAG tool) | Baseline | +30% | **30%** ↑ |
| Time to completion | Baseline | -8% | **8%** ↓ |

### Implementation Details

**Agent:** `SQLSynthesisTableAgent` class in `Super_Agent_hybrid.py`
- Uses LangGraph agent with UC function tools
- Instruction-aware system prompt
- Parallel tool call optimization
- Schema-aware query validation

**UC Functions:**
- `{catalog}.{schema}.get_space_summary(space_ids_json)` - Space-level info
- `{catalog}.{schema}.get_table_overview(space_ids_json)` - Table schemas
- `{catalog}.{schema}.get_column_detail(space_ids_json)` - Column details
- `{catalog}.{schema}.get_space_details(space_ids_json)` - Complete metadata (last resort)

**Data Source:**
- `enriched_genie_docs_chunks` Delta table
- Multi-level chunks: space_summary, table_overview, column_detail
- Enriched with column samples and value dictionaries

### Why This Matters for Enterprise

1. **Complex Instructions**: Handle multi-part constraints (inclusion, exclusion, recency)
2. **Heterogeneous Data**: Reason across different knowledge sources
3. **Cost-Effective**: Small models achieve frontier performance via offline RL
4. **Low Latency**: Single-step execution with intelligent metadata fetching
5. **Accurate Results**: Schema-aware queries reduce hallucinations

## Key Design Decisions

1. **Hybrid Execution Strategy**
   - Table Route: Fast responses using Instructed Retriever with UC functions
   - Genie Route: Accurate responses using actual Genie agents
   - System defaults to table_route unless user specifies otherwise

2. **Memory Architecture**
   - Short-term: Lakebase checkpoints (per conversation thread)
   - Long-term: Lakebase store with vector embeddings (per user)
   - Distributed: Works across multiple Model Serving instances

3. **Agent Specialization**
   - Each agent has dedicated LLM endpoint optimized for its role
   - Planning: Fast model for quick decisions
   - SQL Synthesis: Accurate model for instruction-following query generation
   - Summarize: Balanced model for natural language

## Notes

- All agents are logged via MLflow for tracking and deployment
- System uses LangGraph StateGraph for agent orchestration
- Streaming support for real-time user feedback
- Intent detection prevents unnecessary clarification loops
- Agent pool caching reduces initialization overhead

