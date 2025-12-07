@Notebooks/02_Table_MetaInfo_Enrichment.py 
1. in 'enriched_doc' dict, add table description, synthesize the table description using all column enriched metadata, put under 'enriched_table' dict as a field
2. in 'enriched_doc' dict, if space_description is empty, synthesis the space description using all table enriched metadata; otherwise, use original space_description asis.
3. in `create_multi_level_chunks` function, for 'space_summary' chunk, include both the space_description and the table_description from all tables inside the space
4. in `create_multi_level_chunks` function, for 'table_overview' chunk, include table_description 
5. Within `create_multi_level_chunks` function, also include a chunk_type == 'space_details', which include very thing from enriched_doc dict for a space, so later I can decide whether to use 'space_summary' for speed or 'space_details' for precision in VS for relevant spaces;  