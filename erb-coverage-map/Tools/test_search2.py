import json

log_path = r'C:\Users\User\.gemini\antigravity-ide\brain\77a5117a-687c-42d8-ba9e-04cdac62d644\.system_generated\logs\transcript.jsonl'
app_js = ""
index_html = ""

try:
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
            except: continue
            
            # Check TOOL_RESPONSE
            if data.get('type') == 'TOOL_RESPONSE':
                content = data.get('content', '')
                if 'maplibregl.Map' in content and 'addLayer' in content:
                    app_js = content
                if '<div id="map"></div>' in content and 'maplibre-gl' in content:
                    index_html = content
            
            # Check TOOL_CALL
            if data.get('type') == 'TOOL_CALL':
                for call in data.get('tool_calls', []):
                    if call.get('name') in ['write_to_file', 'replace_file_content']:
                        args = call.get('arguments', {})
                        if 'app.js' in args.get('TargetFile', ''):
                            # if it's a full write, capture it.
                            if call['name'] == 'write_to_file':
                                app_js = args.get('CodeContent', '')
                        if 'index.html' in args.get('TargetFile', ''):
                            if call['name'] == 'write_to_file':
                                index_html = args.get('CodeContent', '')

except Exception as e:
    print(f"Error: {e}")

if app_js:
    with open('app_recovered.js', 'w', encoding='utf-8') as f:
        f.write(app_js)
    print(f"Recovered app.js ({len(app_js)} chars)")

if index_html:
    with open('index_recovered.html', 'w', encoding='utf-8') as f:
        f.write(index_html)
    print(f"Recovered index.html ({len(index_html)} chars)")
