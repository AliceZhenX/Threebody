# llm.py
# -*- coding: utf-8 -*-
"""
大模型模块：
- analyze_query：结构化理解用户查询（关键词/问题/snippet 原文片段）
- summarize_with_llm：根据 prompt 生成回答（由 app.py 构造 prompt）
"""

from typing import Dict, Any
import json
from zhipuai import ZhipuAI

# 记得换成你自己的 key，或改成从环境变量读取
client = ZhipuAI(api_key="dc189be1ea7948e8b7f17b1250c3747a.tKs0JBIe9Q4DS9mr")


# ========= 1. 查询分析：snippet / keyword / question =========

ANALYZE_SYSTEM_PROMPT = """
你是一个“查询理解助手”，只负责分析用户对《三体》三部曲的查询，不直接回答问题。

请注意：
- 用户的查询 q 可能是一个关键词（如“黑暗森林法则”），一个完整问题（如“程心是谁”），
  也可能是小说里的一个“原文片段/名句”（如“前进，前进，不择手段的前进”）。
- 你的任务是输出一个 JSON，描述这个查询的类型、意图、用于检索的 search_query 和关键词列表。

【输出格式】
你必须只输出一个 JSON 对象，不要添加任何其它文字，格式如下：

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
   - "snippet": 查询看起来像小说里的原文片段或名句，例如：
       - 一整句或多句中文，包含大量标点，没有明显“是谁/是什么/为什么”等疑问词；
       - 常见的小说名言、口号、歌谣等。
   - "keyword": 查询主要是名词短语，例如“黑暗森林法则”“歌者文明”“古筝行动”。
   - "question": 查询是完整的问句，例如“程心是谁”“歌者的歌谣具体是什么”。

2. intent：
   - "locate_original": 用户主要想找到这段原文在小说中的位置或全文（通常 query_type=snippet）。
   - "ask_original_text": 用户用问句方式来问“这段原文/歌谣/内容是什么”，例如“歌者的歌谣的内容是什么”。
   - "ask_meaning": 解释概念，例如“黑暗森林法则是什么？”。
   - "ask_character_profile": 介绍人物，例如“程心是谁”“张北海是什么样的人？”。
   - "ask_story_detail": 询问具体情节或事件，例如“古筝行动是怎么执行的？”。
   - "ask_other": 其它不容易分类的情况。

3. search_query：
   - 这是给搜索引擎使用的检索串，要尽量简短直接。
   - 去掉“具体”“内容”“请问”“是什么”“吗”“呢”等疑问成分；
   - 保留核心人物名、组织名、事件名、章节名等；
   - 可以包含多个词，用空格分隔，例如："歌者 歌谣"、"史强 汪淼"、"黑暗森林法则"。

4. keywords：
   - 1~5 个最重要的关键词或短语，每个最好是小说中自然出现的词组。
   - 例如 ["歌者", "歌谣"]、["黑暗森林法则"]、["程心"]、["史强", "汪淼"]。

5. need_original_text：
   - 如果用户明显在要“小说原文/歌词/具体句子”，设为 true，
     典型是 intent 为 "locate_original" 或 "ask_original_text" 的情况；
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
    - 给出 search_query / keywords / need_original_text
    """
    user_prompt = f"用户的原始查询是：{query}\n\n请按照要求输出 JSON。"

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

    # 填补缺失字段（避免后端崩）
    if "query_type" not in data:
        data["query_type"] = "question"
    if "intent" not in data:
        data["intent"] = "ask_other"
    if "search_query" not in data or not str(data["search_query"]).strip():
        data["search_query"] = query
    if "keywords" not in data or not isinstance(data["keywords"], list):
        data["keywords"] = []
    if "need_original_text" not in data:
        data["need_original_text"] = data.get("intent") in ("locate_original", "ask_original_text")

    return data


# ========= 2. 回答生成：由 app.py 构造 prompt，这里只负责调用模型 =========

ANSWER_SYSTEM_PROMPT = """你是一名对刘慈欣《三体》三部曲极其熟悉的讲解助手。

请注意：
1. 回答要基于用户提供的问题和上下文（如果给出），尤其是上下文中的小说原文。
2. 如果给出了原文片段，请以原文为主要依据进行解释，不要随意编造与原文冲突的情节。
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
