# app.py
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify
import html
import traceback

import lucene
from search import search_multi_granularity
from llm import summarize_with_llm

app = Flask(__name__)


def ensure_jvm_attached():
    """
    确保当前线程已经 attach 到 JVM：
    - 第一次调用时如果 VM 还没启动，就 initVM
    - 之后每个新线程都调用 env.attachCurrentThread()
    """
    try:
        env = lucene.getVMEnv()
    except Exception:
        env = None

    if env is None:
        # JVM 还没启动（理论上只会发生一次）
        lucene.initVM(vmargs=["-Djava.awt.headless=true"])
    else:
        # JVM 已经启动，但当前线程需要 attach
        env.attachCurrentThread()


def bracket_to_mark(text: str) -> str:
    """
    把 search.py 中用 [term] 包裹的高亮，转换为 HTML <mark>term</mark>
    同时先做 HTML escape，防止 XSS。
    """
    escaped = html.escape(text)
    return escaped.replace("[", "<mark>").replace("]", "</mark>")


@app.route("/")
def index():
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

    # 2. 先确保当前线程已 attach JVM，再做 Lucene 检索
    try:
        ensure_jvm_attached()
        res = search_multi_granularity(query, top_k_chapters=100)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"搜索失败: {e}"}), 500

    chapters_for_frontend = []
    paragraphs_for_llm = []

    for ch in res.get("chapters", []):
        hit_paras = ch.get("hit_paragraphs") or []
        if not hit_paras:
            continue

        ch_obj = {
            "book": ch.get("book"),
            "chapter": ch.get("chapter"),
            "score": ch.get("score"),
            "paragraphs": [],
        }

        for p in hit_paras:
            # 前端展示用（已经做了 escape + mark 高亮）
            ch_obj["paragraphs"].append({
                "index": p["index"],
                "html": bracket_to_mark(p["text"]),
            })
            # LLM 用
            paragraphs_for_llm.append({
                "book": ch.get("book"),
                "chapter": ch.get("chapter"),
                "text": p["text"],
            })

        chapters_for_frontend.append(ch_obj)

    # 3. 调用 LLM 做总结
    summary = ""
    llm_error = ""
  
    try:
        summary = summarize_with_llm(query)
    except Exception as e:
        traceback.print_exc()
        llm_error = f"LLM 调用失败: {e}"

    return jsonify({
        "query": query,
        "chapters": chapters_for_frontend,
        "summary": summary,
        "llm_error": llm_error,
    })


if __name__ == "__main__":
    # 开发阶段用 debug=True 即可
    app.run(host="0.0.0.0", port=5000, debug=True)
