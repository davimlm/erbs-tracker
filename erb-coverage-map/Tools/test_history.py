import os
import glob
import codecs

history_path = os.path.expandvars(r'%APPDATA%\Code\User\History')
if not os.path.exists(history_path):
    print("No VSCode history found.")
    exit()

best_file = None
best_time = 0

for root, dirs, files in os.walk(history_path):
    for f in files:
        filepath = os.path.join(root, f)
        try:
            mtime = os.path.getmtime(filepath)
            # only check files modified in the last 2 days
            import time
            if time.time() - mtime > 86400 * 2: continue
            
            with codecs.open(filepath, 'r', 'utf-8', errors='ignore') as file:
                content = file.read()
                if 'drivetest_radar_layer' in content and 'mapa.addLayer(' in content and 'hud-cpu' in content:
                    if mtime > best_time:
                        best_time = mtime
                        best_file = filepath
        except:
            pass

if best_file:
    print(f"Found match in {best_file}")
    with open('app_restored_from_history.js', 'w', encoding='utf-8') as f:
        with codecs.open(best_file, 'r', 'utf-8', errors='ignore') as source:
            f.write(source.read())
    print("Saved to app_restored_from_history.js")
else:
    print("No matching file found in VSCode history.")

