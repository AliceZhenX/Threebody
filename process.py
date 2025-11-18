# prepare_docs.py
# -*- coding: utf-8 -*-
import re
from typing import List, Dict

ALL_FILE = "threebody.txt"


# ====== 三体1 ======

def split_book1(text: str) -> List[Dict]:
    """切分《三体1》：按 '第X章 标题' 分章"""

    # 去掉开头的“三体1”
    text = re.sub(r"^三体1\s*", "", text, count=1)
    text = text.lstrip("\n")

    # 按行首的 “第\d+章 ...” 切
    parts = re.split(r"(?m)^(第\d+章[^\n]*?)\n", text)

    docs: List[Dict] = []
    preface = parts[0].strip()  # 万一前面还有点东西，就并到第1章里

    for i in range(1, len(parts), 2):
        title_line = parts[i].strip()
        body = parts[i + 1]

        if i == 1 and preface:
            body = preface + "\n" + body

        m = re.match(r"第(\d+)章\s*(.*)", title_line)
        if m:
            ch_no = int(m.group(1))
            ch_title = m.group(2).strip()
        else:
            ch_no = None
            ch_title = title_line

        docs.append({
            "book": "三体1",
            "chapter_no": ch_no,
            "chapter": ch_title or title_line,
            "content": body.strip(),
        })

    return docs


# ====== 三体2：黑暗森林 ======

def split_book2(text: str) -> List[Dict]:
    """切分 三体2：黑暗森林"""
    # 去掉开头的标题行 “三体2：黑暗森林”
    text = re.sub(r"^三体2：黑暗森林\s*", "", text, count=1)

    docs = []

    # --- 序章 ---
    m_seq = re.search(r"序章\s*\n", text)
    m_part1 = re.search(r"上部 面壁者\s*\n", text)
    if m_seq and m_part1:
        seq_start = m_seq.end()
        seq_end = m_part1.start()
        content = text[seq_start:seq_end].strip()
        docs.append({
            "book": "三体2",
            "chapter": "序章",
            "section": "",
            "content": content,
        })

    # 三个部分的位置
    m_u = re.search(r"上部 面壁者\s*\n", text)
    m_m = re.search(r"中部 咒语\s*\n", text)
    m_l = re.search(r"下部 黑暗森林\s*\n", text)

    pos_u = m_u.start() if m_u else -1
    pos_m = m_m.start() if m_m else -1
    pos_l = m_l.start() if m_l else -1

    # 找到所有 “危机纪年第X年，三体舰队距太阳系Y光年” 的小标题
    sub_matches = list(re.finditer(r"危机纪年第[^\n]*光年", text))

    for m in sub_matches:
        heading = m.group(0)
        start = m.start()

        # 判断属于哪个大部分
        if pos_u != -1 and start >= pos_u and (pos_m == -1 or start < pos_m):
            part = "上部 面壁者"
        elif pos_m != -1 and start >= pos_m and (pos_l == -1 or start < pos_l):
            part = "中部 咒语"
        else:
            part = "下部 黑暗森林"

        # 章节内容：从该 heading 起，到下一个 heading 或 本书结束
        # 注意这里用 book2 区间内的 text
        next_start = None
        for n in sub_matches:
            if n.start() > start:
                next_start = n.start()
                break
        if next_start is None:
            # 到三体3开头或 text 结尾
            content = text[start:].strip()
        else:
            content = text[start:next_start].strip()

        docs.append({
            "book": "三体2",
            "section": part,
            "chapter": heading,
            "content": content,
        })

    return docs


# ====== 三体3：死神永生 ======

def split_book3(text: str) -> List[Dict]:
    """切分《三体3》：纪年对照表 + 第X部 + 每部内的【小节】"""

    # 去掉开头的“三体3：死神永生”
    text = re.sub(r"^三体3[:：].*\n*", "", text, count=1)
    text = text.lstrip("\n")

    docs: List[Dict] = []

    # 纪年对照表 + 第一部 之前的东西
    m_first_part = re.search(r"(?m)^第[一二三四五六七八九十]+部\s*\n", text)
    if m_first_part:
        preface = text[:m_first_part.start()].strip()
        if preface:
            docs.append({
                "book": "三体3",
                "section": None,
                "chapter": "纪年对照表及序章",
                "content": preface,
            })
        rest = text[m_first_part.start():]
    else:
        rest = text

    # 外层：第X部
    parts = re.split(r"(?m)^(第[一二三四五六七八九十]+部)\s*\n", rest)
    prefix = parts[0].strip()

    for i in range(1, len(parts), 2):
        section = parts[i].strip()      # “第一部”“第二部”...
        body = parts[i + 1]

        if i == 1 and prefix:
            body = prefix + "\n" + body

        # 内层：每一部里的 【小节】 标题
        # 允许前面有空格 / 全角空格
        sub_parts = re.split(r"(?m)^([ \t　]*【[^】]+】)\s*\n", body)

        # 小节前面的内容，作为这一部的“序”
        pre_chapter = sub_parts[0].strip()
        if pre_chapter:
            docs.append({
                "book": "三体3",
                "section": section,
                "chapter": section + "·序",
                "content": pre_chapter,
            })

        # 遍历所有 【标题】
        for j in range(1, len(sub_parts), 2):
            head = sub_parts[j].strip()
            content = sub_parts[j + 1] if j + 1 < len(sub_parts) else ""
            title = head.strip("【】 \n　")  # 去掉中英文空格和【】

            docs.append({
                "book": "三体3",
                "section": section,
                "chapter": title,
                "content": content.strip(),
            })

    return docs


# ====== 总入口 ======

def load_all_docs() -> List[Dict]:
    with open(ALL_FILE, "r", encoding="utf-8") as f:
        full = f.read()

    # 粗切成三部
    idx1 = full.find("三体1")
    idx2 = full.find("三体2")
    idx3 = full.find("三体3")

    b1 = full[idx1:idx2]
    b2 = full[idx2:idx3]
    b3 = full[idx3:]

    docs: List[Dict] = []
    docs += split_book1(b1)
    docs += split_book2(b2)
    docs += split_book3(b3)

    # 加一下 id
    for i, doc in enumerate(docs, start=1):
        doc["id"] = i

    return docs


if __name__ == "__main__":
    docs = load_all_docs()
    print("Total docs:", len(docs))
    for d in docs[:5]:
        print(d["book"], d["chapter"][:30])

    import json
    with open("threebody.json", "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)


