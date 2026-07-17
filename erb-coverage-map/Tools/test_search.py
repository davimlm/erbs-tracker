import json
import os

conversations = [
    '32a78b27-343d-43b8-be03-eda9b99bad7a',
    'e05993de-fd8d-4f67-9b8b-ecc538f40879',
    '79fbdb7e-eecf-4aad-bcad-b14d7883cd7b',
    '77a5117a-687c-42d8-ba9e-04cdac62d644'
]
base_dir = r'C:\Users\User\.gemini\antigravity-ide\brain'

last_app_js = ""
last_index_html = ""

for conv in conversations:
    log_path = os.path.join(base_dir, conv, '.system_generated', 'logs', 'transcript.jsonl')
    if not os.path.exists(log_path): continue
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            try:
                data = json.loads(line)
            except: continue
            
            # If the output contains the content of app.js (e.g. from a view_file or run_command)
            if data.get('type') == 'TOOL_RESPONSE' and 'app.js' in data.get('content', ''):
                pass
            
            # Or if it's the model's text containing the code block
            # Actually, the system stores the file content in TOOL_RESPONSE if I ran python -c "print(open('app.js').read())"
            
            # Let's just dump ALL tool responses containing 'maplibregl' or 'executarAnaliseEspacial' to a file to search manually
