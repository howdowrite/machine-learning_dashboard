content = open('dashboard.html', encoding='utf-8').read()
idx = content.find('"Western":{"score"')
if idx == -1:
    idx = content.find('"Western":')
if idx == -1:
    print("Western key not found in top_by_genre")
else:
    print("Found Western at index", idx)
    print(content[idx:idx+400])
