import json
import os

conversations = [
    '32a78b27-343d-43b8-be03-eda9b99bad7a',
    'e05993de-fd8d-4f67-9b8b-ecc538f40879',
    '79fbdb7e-eecf-4aad-bcad-b14d7883cd7b',
    '77a5117a-687c-42d8-ba9e-04cdac62d644'
]
base_dir = r'C:\Users\User\.gemini\antigravity-ide\brain'

replacements_app = []
replacements_index = []

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
                    if call.get('name') in ['replace_file_content', 'write_to_file', 'multi_replace_file_content']:
                        args = call.get('arguments', {})
                        if 'app.js' in args.get('TargetFile', ''):
                            content = args.get('ReplacementContent', args.get('CodeContent', ''))
                            if not content and 'ReplacementChunks' in args:
                                for chunk in args['ReplacementChunks']:
                                    if len(chunk.get('ReplacementContent', '')) > 2000:
                                        replacements_app.append(chunk.get('ReplacementContent', ''))
                            elif len(content) > 2000:
                                replacements_app.append(content)
                        if 'index.html' in args.get('TargetFile', ''):
                            content = args.get('ReplacementContent', args.get('CodeContent', ''))
                            if not content and 'ReplacementChunks' in args:
                                for chunk in args['ReplacementChunks']:
                                    if len(chunk.get('ReplacementContent', '')) > 1000:
                                        replacements_index.append(chunk.get('ReplacementContent', ''))
                            elif len(content) > 1000:
                                replacements_index.append(content)

if replacements_app:
    with open('app_recovered.js', 'w', encoding='utf-8') as f:
        f.write(replacements_app[-1]) # write the last big replacement
    print(f"Recovered app.js ({len(replacements_app[-1])} chars)")

if replacements_index:
    with open('index_recovered.html', 'w', encoding='utf-8') as f:
        f.write(replacements_index[-1])
    print(f"Recovered index.html ({len(replacements_index[-1])} chars)")
