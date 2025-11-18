# llm.py
# -*- coding: utf-8 -*-
"""
大模型模块：
- analyze_query：结构化理解用户查询（keyword / question / snippet + intent）
- summarize_with_llm：根据 prompt 生成回答（由 app.py 构造 prompt）
"""

from typing import Dict, Any
import json

from zhipuai import ZhipuAI

# TODO: 换成你自己的 key 或改成从环境变量读取
client = ZhipuAI(api_key="my key")


# ========= 1. 查询分析：7 种场景都走这里 =========

ANALYZE_SYSTEM_PROMPT = """
你是一个“查询理解助手”，只负责分析用户对《三体》三部曲的查询，不直接回答问题。

用户的查询 q 可能属于以下几类：
1) 单个关键词：例如 “黑暗森林”、“歌者”、“歌者歌谣”
2) 普通问句：例如 “程心是谁”、“史强和汪淼是什么关系”
3) 概念问句：例如 “黑暗森林法则是什么？”
4) 基于原文内容的问句：例如 “歌者的歌谣的内容是什么”、“地球与三体大战时有哪些舰队名”
5) 基于原文的人物生平类：例如 “维德在三体中担当什么职位，干了什么”
6) 基于原文的章节标题：例如 “‘时间之外的往事’的完整内容是什么”
7) 原文引用片段：例如 “前进，前进，不择手段的前进！”

【输出格式】
你必须只输出一个 JSON 对象，不要添加任何其它文字，例如：

{
  "query_type": "snippet" | "keyword" | "question",
  "intent": "locate_original" | "ask_original_text" | "ask_meaning" |
            "ask_character_profile" | "ask_story_detail" | "ask_other",
  "search_query": "用来做检索的短字符串，可以包含多个词，用空格分隔",
  "keywords": ["关键词1", "关键词2", "..."],
  "need_original_text": true or false
}

字段解释：

1. query_type：
   - "snippet": 查询本身就是小说中的原文片段或名句，例如：
       - “前进，前进，不择手段的前进！”
   - "keyword": 查询主要是名词短语，例如：
       - “黑暗森林”、“歌者歌谣”
   - "question": 查询是完整问句，例如：
       - “程心是谁”、“歌者的歌谣的内容是什么”

2. intent：
   - "locate_original": 用户主要想找到原文片段或名句在小说中的位置或全文（通常 query_type=snippet）。
   - "ask_original_text": 用户用问句方式询问某段原文/歌谣/列表型内容，例如：
       - “歌者的歌谣的内容是什么”
       - “地球与三体大战时有哪些舰队名”
       - “‘时间之外的往事’的完整内容是什么”
   - "ask_meaning": 解释概念，例如：
       - “黑暗森林法则是什么？”
   - "ask_character_profile": 介绍人物，例如：
       - “程心是谁”
   - "ask_story_detail": 询问具体情节或人物事迹，例如：
       - “史强和汪淼是什么关系”
       - “维德在三体中担当什么职位，干了什么”
   - "ask_other": 其它不容易分类的情况。

3. search_query：
   - 这是给搜索引擎使用的检索串，要尽量简短直接。
   - 去掉“具体”“内容”“请问”“是什么”“有哪些”“吗”“呢”等疑问成分；
   - 保留核心人物名、组织名、事件名、章节名等；
   - 可以包含多个词，用空格分隔，例如：
       - “黑暗森林”
       - “程心”
       - “史强 汪淼”
       - “歌者 歌谣”
       - “时间之外的往事”

4. keywords：
   - 1~5 个最重要的关键词或短语，每个最好是小说中自然出现的词组。
   - 例如 ["黑暗森林"], ["程心"], ["史强", "汪淼"], ["歌者", "歌谣"], ["时间之外的往事"]。

5. need_original_text：
   - 如果用户明显在要“小说原文/歌词/具体句子/完整列表内容”，设为 true：
       - intent 为 "locate_original" 或 "ask_original_text" 的情况；
       - 或者问题中出现“原文、原话、原句、歌谣、歌词、完整内容、全文、内容、舰队名”等词语。
   - 如果用户只是要解释、总结或人物介绍，设为 false。
"""


def _safe_json_loads(text: str) -> Dict[str, Any]:
    """从大模型输出中尽量抠出 JSON 对象"""
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass

    return {}


def analyze_query(query: str) -> Dict[str, Any]:
    """
    使用 LLM 分析查询：
    - 判断 query_type (snippet/keyword/question)
    - 推断 intent
    - 返回 search_query / keywords / need_original_text
    """
    user_prompt = f"用户的原始查询是：{query}\n\n请严格按照上面的说明，只输出一个 JSON 对象。"

    resp = client.chat.completions.create(
        model="glm-4-flash",
        messages=[
            {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        top_p=0.9,
        max_tokens=400,
        stream=False,
    )

    content = resp.choices[0].message.content.strip()
    data = _safe_json_loads(content)

def analyze_query(query: str) -> Dict[str, Any]:
    user_prompt = f"用户的原始查询是：{query}\n\n请严格按照上面的说明，只输出一个 JSON 对象。"

    resp = client.chat.completions.create(
        model="glm-4-flash",
        messages=[
            {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        top_p=0.9,
        max_tokens=400,
        stream=False,
    )

    content = resp.choices[0].message.content.strip()
    data = _safe_json_loads(content)

    q = (query or "").strip()

    # 1. 基本兜底
    if data.get("query_type") not in ("snippet", "keyword", "question"):
        data["query_type"] = "question"
    if "intent" not in data:
        data["intent"] = "ask_other"
    if "search_query" not in data or not str(data["search_query"]).strip():
        data["search_query"] = q
    if "keywords" not in data or not isinstance(data["keywords"], list):
        data["keywords"] = []
    if "need_original_text" not in data:
        data["need_original_text"] = data.get("intent") in ("locate_original", "ask_original_text")

    # 2. 字面包含“原文/内容/歌谣/歌词/完整/舰队名”等，强制视为要原文
    ori_hints = ["原文", "原话", "原句", "歌谣", "歌词", "完整内容", "完整", "全文", "内容", "舰队名", "舰队名称","名称"]
    if any(h in q for h in ori_hints):
        data["need_original_text"] = True
        if data.get("intent") not in ("locate_original", "ask_original_text"):
            data["intent"] = "ask_original_text"
        if data.get("query_type") == "keyword":
            data["query_type"] = "question"

    # 3. 只要是 snippet，就默认是在找原文位置
    if data.get("query_type") == "snippet":
        data["need_original_text"] = True
        if data.get("intent") not in ("locate_original", "ask_original_text"):
            data["intent"] = "locate_original"

    return data



# ========= 2. 回答生成：由 app.py 构造 prompt，这里只负责调用模型 =========

ANSWER_SYSTEM_PROMPT = """你是一名对刘慈欣《三体》三部曲极其熟悉的讲解助手。

请注意：
1. 回答要基于用户提供的问题和上下文（如果给出），尤其是上下文中的小说原文。
2. 如果给出了原文片段，请以原文为主要依据进行解释或抽取答案，不要随意编造与原文冲突的情节。
3. 回答使用自然、流畅的中文，不要加项目符号或标题，不要使用【】等装饰性前缀。
4. 当你不确定某个细节时，可以委婉说明“不确定/原文没有明确说明”，不要捏造。"""


def summarize_with_llm(prompt: str) -> str:
    """
    接收一个完整的 prompt（由 app.py 组织好，包含问题 + 可选上下文），
    返回模型生成的回答文本。
    """
    resp = client.chat.completions.create(
        model="glm-4-flash",
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        top_p=0.9,
        max_tokens=800,
        stream=False,
    )

    return resp.choices[0].message.content.strip()

