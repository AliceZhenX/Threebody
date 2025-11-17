# prepare_docs.py
import re
from typing import List, Dict

ALL_FILE = "threebody.txt"


def split_book1(text: str) -> List[Dict]:
    """切分 三体1：按 '第X章 标题' 分章"""
    # 去掉开头的"三体1"等标题
    text = re.sub(r"^三体1\s*", "", text, count=1)

    # 以 "第X章 标题" 为分界
    parts = re.split(r"(第\d+章[^\n]*\n)", text)
    docs = []
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()          # 例如 "第1章 科学边界"
        content = parts[i + 1].strip()
        m = re.match(r"第(\d+)章\s*(.*)", heading)
        chapter_no = int(m.group(1)) if m else None
        title = m.group(2) if m else heading
        docs.append({
            "book": "三体1",
            "section": "",  # 三体1没有明确的section划分
            "chapter": title,
            "content": content,
        })
    return docs


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


def split_book3(text: str) -> List[Dict]:
    """切分 三体3：死神永生"""
    # 去掉开头 “三体3：死神永生”
    text = re.sub(r"^三体3：死神永生\s*", "", text, count=1)

    docs: List[Dict] = []

    # --- 纪年对照表 ---
    table_pos = text.find("纪年对照表")
    if table_pos != -1:
        # 找到第一个 “第一部”
        m_part1 = re.search(r"第[一二三四五六]部\s*\n", text[table_pos:])
        if m_part1:
            part1_abs_pos = table_pos + m_part1.start()
        else:
            part1_abs_pos = len(text)
        table_content = text[table_pos:part1_abs_pos].strip()
        docs.append({
            "book": "三体3",
            "section": "",
            "chapter": "纪年对照表",
            "content": table_content,
        })
        rest = text[part1_abs_pos:]
    else:
        rest = text

    # --- 各部 + 【小节】 ---
    # 先分割各大部分，只提取"第一部"、"第二部"等作为section
    parts = re.split(r"(第[一二三四五六]部)\s*[^\n]*\n", rest)
    for i in range(1, len(parts), 2):
        section = parts[i].strip()      # 只保留"第一部"、"第二部"等
        part_body = parts[i + 1]

        # 用【...】分小节，这些才是真正的chapter
        sub_parts = re.split(r"(【[^】]{3,80}】\s*)", part_body)
        for j in range(1, len(sub_parts), 2):
            sub_head = sub_parts[j]
            sub_body = sub_parts[j + 1]
            # 确保完全移除【】符号，特别是末尾的】
            chapter_title = sub_head.replace("【", "").replace("】", "").strip(" \n")
            content = sub_body.strip()

            docs.append({
                "book": "三体3",
                "section": section,
                "chapter": chapter_title,
                "content": content,
            })

    return docs


def load_all_docs() -> List[Dict]:
    """从 threebody1.txt 中切出三体1+2+3 的所有章节 doc"""
    raw = open(ALL_FILE, encoding="utf-8").read()

    pos1 = raw.find("三体1")
    pos2 = raw.find("三体2")
    pos3 = raw.find("三体3")

    book1_txt = raw[pos1:pos2]
    book2_txt = raw[pos2:pos3]
    book3_txt = raw[pos3:]

    docs: List[Dict] = []
    docs += split_book1(book1_txt)
    docs += split_book2(book2_txt)
    docs += split_book3(book3_txt)
    
    # 为所有章节添加唯一的id编码
    for i, doc in enumerate(docs):
        # 使用格式：threebody_{序号}
        doc["id"] = i
    
    return docs


if __name__ == "__main__":
    docs = load_all_docs()
    print("Total docs:", len(docs))
    # 简单看几条
    for d in docs[:5]:
        print(d["book"], d["chapter"][:30])
    with open("threebody.json", "w", encoding="utf-8") as f:
        import json
        json.dump(docs, f, ensure_ascii=False, indent=2)