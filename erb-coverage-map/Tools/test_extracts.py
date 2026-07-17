import os
for f in ['extracted_code5.txt', 'extracted_code6.txt', 'extracted_cov_full.txt']:
    if os.path.exists(f):
        print(f"--- {f} ---")
        with open(f, 'r', encoding='utf-8') as file:
            print(file.read()[:500])
