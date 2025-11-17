import json

with open("threebody.json", "r", encoding="utf-8") as f:
    docs = json.load(f)

keyword = "蓝色空间号"

cnt = 0
for d in docs:
    text = d.get("content", "") or ""
    if keyword in text:
        cnt += 1
        print("命中章节：", d.get("book"), d.get("chapter"))
        # 如果想看一小段，可以再打印 text[:200]

print(f"包含{keyword}的章节数：", cnt)


keyword = "歌者"
found = False
count = 0

with open("threebody.txt", "r", encoding="utf-8") as f:
    for line in f:
        if keyword in line:
            found = True
            print(f"找到了: {line.strip()}")
            
            count += 1
            if count >= 10:
                break


if not found:
    print("没有找到关键词")