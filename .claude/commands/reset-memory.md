Reset the agent's cross-run memory (seen conferences list).

Steps:
1. Read and display current memory_store.json content
2. Show: number of tracked conferences, date of last run
3. Ask the user to confirm before proceeding ("Type YES to confirm reset")
4. If confirmed: write `{"seen_acronyms": [], "calendar_ids": {}, "runs": []}` to memory_store.json
5. Show confirmation with new file content
6. Warn: "Next agent run will re-evaluate all conferences including previously tracked ones"
