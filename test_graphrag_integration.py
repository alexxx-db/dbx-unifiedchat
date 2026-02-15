"""
Test GraphRAG integration with real Unity Catalog data.
"""
import json
import sys
from pathlib import Path
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

# Add GraphRAG module to path
graphrag_path = Path(__file__).parent / "tables_to_genies" / "graphrag"
sys.path.insert(0, str(graphrag_path))

from build_table_graph import GraphRAGTableGraphBuilder

def test_graphrag_build():
    print("🚀 Testing GraphRAG Table Graph Builder...")
    
    # Initialize Databricks Client
    config = Config()
    client = WorkspaceClient(config=config)
    warehouse_id = "a4ed2ccbda385db9"
    table_fqn = "serverless_dbx_unifiedchat_catalog.gold.enriched_table_metadata"

    print(f"📊 Fetching metadata from {table_fqn}...")
    
    try:
        # Fetch enriched tables
        res = client.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=f"SELECT table_fqn, enriched_doc FROM {table_fqn} WHERE enriched = true",
            wait_timeout="30s"
        )
        
        if not res.result or not res.result.data_array:
            print("❌ No enriched tables found.")
            return

        print(f"✅ Found {len(res.result.data_array)} enriched tables.")
        
        # Convert to GraphRAG format
        enriched_tables_data = []
        for row in res.result.data_array:
            fqn = row[0]
            doc = json.loads(row[1])
            parts = fqn.split('.')
            
            enriched_tables_data.append({
                'fqn': fqn,
                'catalog': parts[0],
                'schema': parts[1],
                'table': parts[2],
                'column_count': doc.get('total_columns', 0),
                'columns': [{'name': col['column_name']} for col in doc.get('enriched_columns', [])],
                'enriched': True
            })

        # Build graph using GraphRAG
        print("\n🏗️ Building graph with GraphRAG...")
        builder = GraphRAGTableGraphBuilder()
        
        # Extract entities
        print("  1. Extracting entities...")
        entities = builder.extract_entities(enriched_tables_data)
        print(f"     ✓ Found {len(entities['tables'])} tables")
        print(f"     ✓ Found {len(entities['schemas'])} schemas")
        print(f"     ✓ Found {len(entities['columns'])} unique column names")
        
        # Detect relationships
        print("  2. Detecting relationships...")
        relationships = builder.detect_relationships(entities)
        print(f"     ✓ Detected {len(relationships)} relationships")
        
        # Build full graph
        print("  3. Building NetworkX graph with community detection...")
        G = builder.build_graph(enriched_tables_data)
        print(f"     ✓ Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        
        # Community detection results
        communities = builder.communities
        print(f"     ✓ Communities: {len(communities)} detected")
        for comm_id, tables in list(communities.items())[:3]:
            table_names = [t.split('.')[-1] for t in tables]
            print(f"       Community {comm_id}: {', '.join(table_names[:5])}")
        
        # Convert to Cytoscape format
        print("  4. Converting to Cytoscape format...")
        cytoscape_data = builder.to_cytoscape_format()
        print(f"     ✓ Generated {len(cytoscape_data['elements'])} elements")
        
        # Sample relationships
        print("\n🔗 Sample Relationships:")
        for rel in relationships[:10]:
            source_name = rel['source'].split('.')[-1]
            target_name = rel['target'].split('.')[-1]
            print(f"  {source_name} <-> {target_name}")
            print(f"    Weight: {rel['weight']}, Types: {rel['types']}")

        print("\n✅ GraphRAG Integration Test PASSED!")

    except Exception as e:
        print(f"❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_graphrag_build()
