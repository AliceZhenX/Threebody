# llm.py
# -*- coding: utf-8 -*-
"""
大模型回答模块：
- 只根据用户输入的 query 来回答
- 如果像问题：回答问题
- 如果像关键词/短语：解释该人物/概念/事件
- 不依赖检索到的段落，不输出任何标题或花哨格式
"""

from typing import List, Dict
import re
from zhipuai import ZhipuAI

# 用你的实际 API Key（建议和 use.py 保持一致）
client = ZhipuAI(api_key="my key")


def _detect_mode(query: str) -> str:
    """
    粗略判断当前输入是“问题”（qa）还是“关键词/短语”（keyword）
    """
    if not query:
        return "keyword"

    q = query.strip()

    # 常见疑问词
    interrogatives = [
        "是谁", "是什么", "为什么", "为何",
        "怎么", "如何", "怎样",
        "在哪", "在哪里",
        "什么时候", "何时",
        "多少", "几个人", "几个",
        "是否", "是不是",
        "哪一", "哪位", "哪个",
        "吗", "么"
    ]

    if q.endswith(("?", "？")):
        return "qa"
    if any(word in q for word in interrogatives):
        return "qa"

    return "keyword"


SYSTEM_PROMPT = """你是一名对刘慈欣《三体》三部曲（《三体》《三体II：黑暗森林》《三体III：死神永生》）极其熟悉的讲解助手。
你已经完整阅读并记住三部曲中的主要人物、势力、时间线、关键事件和核心思想。

请注意：
1. 回答时可以、也应该充分依靠你对《三体》三部曲的先验知识，不需要引用用户提供的原文片段。
2. 用户的输入可能是一个问题，也可能只是一个人物/名词/事件的关键词。
3. 回答要用自然、流畅的中文，不要使用列表符号或小标题，不要加【】等装饰性前缀。
4. 回答应尽量准确，避免与原著严重冲突；不确定的地方可以委婉说明，而不是瞎编。"""


def summarize_with_llm(query: str, *_args, **_kwargs) -> str:
    """
    对外统一接口：
    - 兼容原来的签名 summarize_with_llm(query, paragraphs)，多余参数会被忽略
    - 内部只根据 query 来回答
    """
    mode = _detect_mode(query)

    if mode == "qa":
        # 问答模式：直接回答问题
        user_content = (
            f"用户的问题是：{query}\n\n"
            "请直接、清楚地回答这个问题。"
            "可以结合你对《三体》三部曲完整剧情的了解进行解释，"
            "但不要输出项目符号、编号或标题，只用一到几段自然语言回答。"
        )
    else:
        # 关键词模式：解释人物/概念/事件
        user_content = (
            f"用户给出的关键词或短语是：{query}\n\n"
            "请解释这个词在《三体》三部曲中的含义和背景，"
            "说明它涉及到的主要人物、势力或事件，以及它在故事中的重要性。"
            "同样只用自然语言一到几段话来回答，不要加标题或列表符号。"
        )

    resp = client.chat.completions.create(
        model="glm-4-flash",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.9,
        top_p=0.7,
        max_tokens=800,
        stream=False,
    )

    return resp.choices[0].message.content.strip()

