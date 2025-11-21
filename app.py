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
    split_paragraphs,
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

def select_snippet_sentence(query: str, analysis: dict, res: dict,
                            max_chapters: int = 5) -> str:
    """
    针对 snippet / 原文引用类查询：
      - 在若干章节中按“句子级”精确定位该句话；
      - 优先整串匹配，其次按关键词密度挑句；
      - 返回该句前后各一句作为上下文。
    """
    raw_query = (query or "").strip()
    keywords = analysis.get("keywords") or []
    sq = (analysis.get("search_query") or raw_query).strip()
    query_terms = keywords or get_query_terms(sq)

    chapters = res.get("chapters") or []
    if not chapters:
        return ""

    best_ctx = ""
    best_score = 0.0

    for ch in chapters[:max_chapters]:
        doc_id = str(ch.get("doc_id"))
        raw_content = DOC_BY_ID.get(doc_id, {}).get("content", "") or ""
        if not raw_content:
            continue

        sents = split_sentences(raw_content)

        # 1) 优先整串匹配：句子里直接包含整句 query
        if raw_query and len(raw_query) >= 4:
            for i, s in enumerate(sents):
                if raw_query in s:
                    start = max(0, i - 1)
                    end = min(len(sents), i + 2)
                    return "".join(sents[start:end]).strip()

        # 2) 否则按关键词密度挑选句子
        for i, s in enumerate(sents):
            score = 0.0
            for t in query_terms:
                if t and t in s:
                    score += len(t)
            if score > best_score:
                best_score = score
                start = max(0, i - 1)
                end = min(len(sents), i + 2)
                best_ctx = "".join(sents[start:end]).strip()

    return best_ctx

def build_brief_context(query: str, analysis: dict, res: dict,
                        max_chapters: int = 5,
                        max_sents: int = 6,
                        max_chars: int = 2000) -> str:
    """
    为 LLM 构造“精简上下文”：
      - 从若干章节中选出最相关的少量句子，而不是整段大段原文；
      - 控制总句数和总字符数，避免噪声和干扰。
    """
    keywords = analysis.get("keywords") or []
    sq = (analysis.get("search_query") or query).strip()
    query_terms = keywords or get_query_terms(sq)

    chapters = res.get("chapters") or []
    context_sents = []
    used_chars = 0

    for ch in chapters[:max_chapters]:
        doc_id = str(ch.get("doc_id"))
        book = ch.get("book", "")
        chapter_title = ch.get("chapter", "")
        raw_content = DOC_BY_ID.get(doc_id, {}).get("content", "") or ""
        if not raw_content:
            continue

        sents = split_sentences(raw_content)
        # 对本章每个句子打分，选出得分最高的 1~2 句
        scores = []
        for i, s in enumerate(sents):
            score = 0.0
            for t in query_terms:
                if t and t in s:
                    score += len(t)
            if score > 0:
                scores.append((score, i, s))

        if not scores:
            continue

        scores.sort(key=lambda x: x[0], reverse=True)
        top_local = scores[:2]  # 每章最多取两句

        for _, i, s in top_local:
            snippet = f"[{book}·{chapter_title}] {s}"
            if used_chars + len(snippet) > max_chars:
                return "\n".join(context_sents)
            context_sents.append(snippet)
            used_chars += len(snippet)

            if len(context_sents) >= max_sents:
                return "\n".join(context_sents)

    return "\n".join(context_sents)



def select_snippet(query: str, analysis: dict, res: dict,
                   max_chapters: int = 3) -> str:
    """
    针对 snippet / ask_original_text 场景，从检索结果中截取最相关的原文片段。

    策略：
      1) 在前 max_chapters 个章节里，按“句子”切分；
      2) 如果整串 query 出现在某句中，返回该句前后各 1 句；
      3) 否则按关键词打分，选出得分最高的那句，返回前后各 1 句。
    """
    raw_query = (query or "").strip()
    keywords = analysis.get("keywords") or []
    sq = (analysis.get("search_query") or raw_query).strip()
    query_terms = keywords or get_query_terms(sq)

    chapters = res.get("chapters") or []
    if not chapters:
        return ""

    # 1) 尝试整串匹配（适合“前进，前进，不择手段的前进”这种）
    if raw_query and len(raw_query) >= 4:  # 太短的就不做整串匹配
        for ch in chapters[:max_chapters]:
            doc_id = str(ch.get("doc_id"))
            raw_content = DOC_BY_ID.get(doc_id, {}).get("content", "") or ""
            if not raw_content:
                continue
            sents = split_sentences(raw_content)
            for i, s in enumerate(sents):
                if raw_query in s:
                    start = max(0, i - 1)
                    end = min(len(sents), i + 2)
                    return "".join(sents[start:end]).strip()

    # 2) 按关键词打分选句
    best_sent = ""
    best_score = 0.0
    best_context = ""

    for ch in chapters[:max_chapters]:
        doc_id = str(ch.get("doc_id"))
        raw_content = DOC_BY_ID.get(doc_id, {}).get("content", "") or ""
        if not raw_content:
            continue

        sents = split_sentences(raw_content)
        for i, s in enumerate(sents):
            score = 0.0
            for t in query_terms:
                if t and t in s:
                    score += len(t)
            if score > best_score:
                best_score = score
                best_sent = s
                start = max(0, i - 1)
                end = min(len(sents), i + 2)
                best_context = "".join(sents[start:end]).strip()

    return best_context or best_sent



@app.route("/")
def index():
    # 如果你的模板名是 index.html，就改成 render_template("index.html")
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
    try:
        analysis = analyze_query(query)
    except Exception as e:
        traceback.print_exc()
        analysis = {
            "query_type": "question",
            "intent": "ask_other",
            "search_query": query,
            "keywords": [],
            "need_original_text": False,
        }

    query_type = analysis.get("query_type", "question")
    intent = analysis.get("intent", "ask_other")
    need_original = bool(analysis.get("need_original_text"))

    llm_sq = (analysis.get("search_query") or "").strip()

    # search_query = 原始 query + LLM 提取的 search_query（不要丢掉原词）
    parts = []
    if query:
        parts.append(query)
    if llm_sq and llm_sq != query:
        parts.append(llm_sq)
    search_query = " ".join(parts) if parts else query

    print("[QUERY]", query)
    print("[ANALYSIS]", analysis)
    print("[SEARCH_QUERY]", search_query)

    # 3. 用 search_query 做 Lucene 检索，必要时回退到原始 query
    def run_ir(q_,s_q):
        ensure_jvm_attached()
        if query_type == "snippet":
            return search_multi_granularity(q_, top_k_chapters=10, ir_query= s_q, snippet_mode=True)
        else:    
            return search_multi_granularity(s_q)

    res = run_ir(query, search_query)

    # 如果改写后的检索一个段落都没有命中，则回退用原始 query 再搜一遍
    if not any(ch.get("hit_paragraphs") for ch in res.get("chapters", [])) and search_query.strip() != query.strip():
        res = run_ir(query,search_query)

    # 4. 构造给前端的章节列表 & 给 LLM 的段落列表
    chapters_for_frontend = []
    paragraphs_for_llm = []
    top_paragraphs = []   # ★ 新增：用来给前端展示“命中段落”

    chapters_for_frontend = []
    paragraphs_for_llm = []
    top_snippets = []   # ★ 新名字，用句子填
    
    for ch in res.get("chapters", []):
        hit_paras = ch.get("hit_paragraphs") or []
        hit_sents = ch.get("hit_sentences") or []
        if not hit_paras and not hit_sents:
            continue
        
        ch_obj = {
            "doc_id": ch.get("doc_id"),
            "book": ch.get("book"),
            "chapter": ch.get("chapter"),
            "score": ch.get("score"),
            "paragraphs": [],
        }
    
        # 章节视图用的段落（保持不变）
        for p in hit_paras:
            html_para = bracket_to_mark(p["text"])
            ch_obj["paragraphs"].append({
                "index": p["index"],
                "html": html_para,
            })
            paragraphs_for_llm.append({
                "book": ch.get("book"),
                "chapter": ch.get("chapter"),
                "text": p["text"],
            })
    
        # 顶部“命中片段”用：按句子级别添加
        for s in hit_sents:
            html_sent = bracket_to_mark(s["text"])
            top_snippets.append({
                "doc_id": ch.get("doc_id"),
                "book": ch.get("book"),
                "chapter": ch.get("chapter"),
                "index": s["index"],   # 句子索引
                "html": html_sent,
            })
    
        chapters_for_frontend.append(ch_obj)
    
    # 限制片段数量（比如最多 10 句）
    TOP_SNIPPET_LIMIT = 10
    top_snippets = top_snippets[:TOP_SNIPPET_LIMIT]
    
    # 5. 是否需要截取一个“原文片段”（snippet）
    exact_snippet = ""
    if need_original or query_type == "snippet":
        exact_snippet = select_snippet_sentence(query, analysis, res)

    # 6. 调用 LLM 生成右侧回答
    summary = ""
    llm_error = ""

    try:
        if need_original or query_type == "snippet":
            # —— 4 / 6 / 7：要原文的场景 —— #
            if exact_snippet:
                prompt = (
                    f"用户问题：{query}\n\n"
                    f"下面是小说《三体》中与问题最相关的原文句子及上下文：\n"
                    f"{exact_snippet}\n\n"
                    "请严格根据这段原文回答问题。"
                    "如果问题是“内容是什么/有哪些”，请从原文中直接提取对应内容，"
                    "不要添加原文中没有提到的新内容。"
                )
            else:
                prompt = (
                    f"用户问题：{query}\n\n"
                    "由于没有截取到清晰的原文片段，请尽量根据你对《三体》三部曲的理解回答。"
                )

        elif intent in ("ask_character_profile", "ask_story_detail"):
            # —— 2 / 5：人物生平 / 情节类（维德这种），严格只看上下文 —— #
            context = build_brief_context(query, analysis, res)
            prompt = (
                f"用户问题：{query}\n\n"
                "下面是小说《三体》中和该问题最相关的一些原文句子：\n"
                f"{context}\n\n"
                "请综合这些原文片段，尽量给出一个完整、连贯的回答。"
                "你可以结合你对《三体》三部曲整体剧情的理解做合理补充，"
                "但不要与这些原文片段的事实明显矛盾。"
                "如果某个细节在原文中完全没有体现，可以语气委婉地说明这一点，"
                "但不要频繁强调“原文不足以回答”，而是尽量把能回答的部分说清楚。"
            )

        else:
            # —— 1 / 3 以及其它：概念解释为主，可以结合一点先验知识 —— #
            context = build_brief_context(query, analysis, res)
            prompt = (
                f"用户问题：{query}\n\n"
                "下面是小说《三体》中和该问题相关的部分原文句子：\n"
                f"{context}\n\n"
                "请优先参考这些原文句子，对概念或问题做出解释。"
                "对于抽象概念，你可以适度结合你对《三体》的理解；"
                "但对于具体人物/情节，请以原文为准，不要与原文矛盾。"
            )

        summary = summarize_with_llm(prompt)
    except Exception as e:
        traceback.print_exc()
        llm_error = f"LLM 调用失败: {e}"

    return jsonify({
        "query": query,
        "search_query": search_query,
        "analysis": analysis,           # 方便调试
        "chapters": chapters_for_frontend,
        "top_snippets": top_snippets,   # ★ 新名字
        "summary": summary,
        "exact_answer": exact_snippet,  # 原文片段（前端可以展示“原文摘录”）
        "llm_error": llm_error,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


