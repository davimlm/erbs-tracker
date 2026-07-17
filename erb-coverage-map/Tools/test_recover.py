import json
import os

conversations = [
    '32a78b27-343d-43b8-be03-eda9b99bad7a',
    'e05993de-fd8d-4f67-9b8b-ecc538f40879',
    '79fbdb7e-eecf-4aad-bcad-b14d7883cd7b',
    '77a5117a-687c-42d8-ba9e-04cdac62d644'
]

base_dir = r'C:\Users\User\.gemini\antigravity-ide\brain'

# We'll just look for the last time I printed out or replaced the full content.
# Wait, let's track write_to_file calls for app.js and index.html
app_js_content = ""
index_html_content = ""

for conv in conversations:
    log_path = os.path.join(base_dir, conv, '.system_generated', 'logs', 'transcript.jsonl')
    if not os.path.exists(log_path): continue
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            try:
                data = json.loads(line)
            except: continue
            
            if data.get('type') == 'TOOL_CALL':
                for call in data.get('tool_calls', []):
                    if call.get('name') == 'write_to_file':
                        args = call.get('arguments', {})
                        if 'app.js' in args.get('TargetFile', ''):
                            app_js_content = args.get('CodeContent', '')
                        elif 'index.html' in args.get('TargetFile', ''):
                            index_html_content = args.get('CodeContent', '')
                    elif call.get('name') in ['replace_file_content', 'multi_replace_file_content']:
                        # Applying replacements to our in-memory string is hard without a full diff tool.
                        # We'll just print if it was replaced.
                        args = call.get('arguments', {})
                        if 'app.js' in args.get('TargetFile', ''):
                            pass # We could try to apply it, but let's just see if we found a write_to_file first.

if app_js_content:
    with open('app_recovered.js', 'w', encoding='utf-8') as f:
        f.write(app_js_content)
    print("Recovered app_recovered.js")
if index_html_content:
    with open('index_recovered.html', 'w', encoding='utf-8') as f:
        f.write(index_html_content)
    print("Recovered index_recovered.html")

