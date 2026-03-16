from soulseek_client import search_soulseek

results = search_soulseek("Daft Punk One More Time")

files = extract_files(results)

print("Total files found:", len(files))
for f in files[:10]:
    print(f)

    