# app.py
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify
import html
import traceback

import lucene
from search import (
    search_multi_granularity,
    DOC_BY_ID,
    split_sentences,
    get_query_terms,
)
from llm import analyze_query, summarize_with_llm

app = Flask(__name__)


def ensure_jvm_attached():
    """确保当前线程已经 attach 到 JVM。"""
    try:
        env = lucene.getVMEnv()
    except Exception:
        env = None

    if env is None:
        lucene.initVM(vmargs=["-Djava.awt.headless=true"])
    else:
        env.attachCurrentThread()


def bracket_to_mark(text: str) -> str:
    """
    把 search.py 中用 [term] 包裹的高亮，转换为 HTML <mark>term</mark>；
    同时先做 HTML escape，防止 XSS。
    """
    escaped = html.escape(text)
    return escaped.replace("[", "<mark>").replace("]", "</mark>")


def select_snippet(query: str, analysis: dict, res: dict,
                   max_chapters: int = 3) -> str:
    """
    针对 snippet / ask_original_text 场景，从检索结果中截取最相关的原文片段。

    优先级：
      1) 在前 max_chapters 个章节里，找包含整串 query 的句子；
      2) 否则，根据 analysis['keywords'] 或 search_query 的关键词，
         选出匹配度最高的一句（或几句）作为 snippet。
    """
    raw_query = (query or "").strip()
    keywords = analysis.get("keywords") or []
    search_query = (analysis.get("search_query") or raw_query).strip()
    query_terms = keywords or get_query_terms(search_query)

    chapters = res.get("chapters") or []
    if not chapters:
        return ""

    # 1) 优先：整串原文直接出现的情况
    for ch in chapters[:max_chapters]:
        doc_id = str(ch.get("doc_id"))
        raw_content = DOC_BY_ID.get(doc_id, {}).get("content", "") or ""
        if not raw_content or not raw_query:
            continue

        if raw_query in raw_content:
            sents = split_sentences(raw_content)
            for i, s in enumerate(sents):
                if raw_query in s:
                    start = max(0, i - 1)
                    end = min(len(sents), i + 2)
                    return "".join(sents[start:end]).strip()

    # 2) 根据关键词匹配度选一句
    best_sent = ""
    best_score = 0.0

    for ch in chapters[:max_chapters]:
        doc_id = str(ch.get("doc_id"))
        raw_content = DOC_BY_ID.get(doc_id, {}).get("content", "") or ""
        if not raw_content:
            continue

        for s in split_sentences(raw_content):
            score = 0.0
            for t in query_terms:
                if t and t in s:
                    score += len(t)
            if score > best_score:
                best_score = score
                best_sent = s

    return best_sent.strip() if best_score > 0 else ""


@app.route("/")
def index():
    # 如果你的模板名不是 search.html，这里改成对应文件名
    return render_template("search.html")


@app.route("/api/search", methods=["POST"])
def api_search():
    # 1. 解析请求 JSON
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"请求体不是合法 JSON: {e}"}), 400

    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is empty"}), 400

    # 2. 先让 LLM 理解查询
    analysis = analyze_query(query)
    query_type = analysis.get("query_type", "question")
    intent = analysis.get("intent", "ask_other")

    llm_sq = (analysis.get("search_query") or "").strip()

    # 1. 先假设搜索串就是原始 query
    search_query = query

    # 2. 如果 LLM 提供了额外 search_query，就把它当成“扩展词”
    if llm_sq and llm_sq != query:
        # 对 keyword 类型：原词最重要，扩展词作为补充
        if query_type == "keyword":
            search_query = f"{query} {llm_sq}"
        else:
            # question/snippet：可以同时用原问题和 LLM 提取的关键词
            search_query = f"{query} {llm_sq}"

    need_original = bool(analysis.get("need_original_text"))

    # 3. 用 search_query 做 Lucene 检索
    try:
        ensure_jvm_attached()
        res = search_multi_granularity(search_query, top_k_chapters=10)
        # 如果用改写后的 search_query 没有命中任何段落，则回退用原始 query 再搜一次
        if not any(ch.get("hit_paragraphs") for ch in res.get("chapters", [])) and search_query.strip() != query.strip():
            res = search_multi_granularity(query, top_k_chapters=10)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"搜索失败: {e}"}), 500

    # 4. 构造给前端的章节列表
    chapters_for_frontend = []
    paragraphs_for_llm = []

    for ch in res.get("chapters", []):
        hit_paras = ch.get("hit_paragraphs") or []
        if not hit_paras:
            continue

        ch_obj = {
            "doc_id": ch.get("doc_id"),
            "book": ch.get("book"),
            "chapter": ch.get("chapter"),
            "score": ch.get("score"),
            "paragraphs": [],
        }

        for p in hit_paras:
            ch_obj["paragraphs"].append({
                "index": p["index"],
                "html": bracket_to_mark(p["text"]),
            })
            paragraphs_for_llm.append({
                "book": ch.get("book"),
                "chapter": ch.get("chapter"),
                "text": p["text"],
            })

        chapters_for_frontend.append(ch_obj)

    # 5. 如果是 snippet / 原文类问题，尝试裁出原文片段
    exact_snippet = ""
    if query_type == "snippet" or need_original:
        exact_snippet = select_snippet(query, analysis, res)

    # 6. 调用 LLM 生成回答
    summary = ""
    llm_error = ""

    try:
        # 构造 prompt
        if query_type == "snippet" or need_original:
            # 原文/歌词类问题：以 snippet 为主做解释
            if exact_snippet:
                prompt = (
                    f"用户的问题：{query}\n\n"
                    f"下面是小说中的相关原文片段：\n{exact_snippet}\n\n"
                    "请基于这段原文，用简洁的中文解释它的大意和情感氛围。"
                )
            else:
                prompt = (
                    f"用户的问题：{query}\n\n"
                    "没能在提供的索引中直接截取到原文片段，请基于你对《三体》三部曲的理解回答。"
                )
        else:
            # 一般问答/概念类：先简单用原始问题
            prompt = query

        summary = summarize_with_llm(prompt)
    except Exception as e:
        traceback.print_exc()
        llm_error = f"LLM 调用失败: {e}"

    print("[ANALYSIS]", analysis)

    return jsonify({
        "query": query,
        "search_query": search_query,
        "analysis": analysis,          # 方便调试：前端也可以选择展示
        "chapters": chapters_for_frontend,
        "summary": summary,
        "exact_answer": exact_snippet,  # 原文片段（如果有）
        "llm_error": llm_error,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

