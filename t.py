import json

with open("threebody.json", "r", encoding="utf-8") as f:
    docs = json.load(f)

keyword = "歌者"

cnt = 0
for d in docs:
    text = d.get("content", "") or ""
    if keyword in text:
        cnt += 1
        print("命中章节：", d.get("book"), d.get("chapter"))
        # 如果想看一小段，可以再打印 text[:200]

print(f"包含{keyword}的章节数：", cnt)



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


def normalize(s: str) -> str:
    # 简单处理一下回车和空格，避免无意义的差异
    return s.replace("\r", "")

with open("threebody.txt", "r", encoding="utf-8") as f:
    raw = normalize(f.read())

import json
with open("threebody.json", "r", encoding="utf-8") as f:
    docs = json.load(f)

joined = normalize("".join(d["content"] for d in docs))

print("len(raw) =", len(raw), "len(joined) =", len(joined))