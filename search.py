#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
多粒度搜索《三体》：

- 先用 Lucene 在 content 字段上检索，召回相关 chapter
- 再对原始章节内容做分段、分句：
  - 命中哪些章节 (chapter)
  - 每章中命中的段落 (paragraph)
  - 每段中命中的句子 (sentence)
"""

import os
import re
import json
from typing import List, Dict, Any

import jieba
import lucene
from java.nio.file import Paths
from org.apache.lucene.store import FSDirectory
from org.apache.lucene.index import DirectoryReader
from org.apache.lucene.search import IndexSearcher
from org.apache.lucene.analysis.core import WhitespaceAnalyzer
from org.apache.lucene.queryparser.classic import QueryParser


# ========= 1. 初始化 Lucene Searcher =========

# ===== 加载自定义词典 =====
USER_DICT = "vocab.txt"   # 如果路径不在当前目录，就写成绝对路径或相对路径
if os.path.exists(USER_DICT):
    jieba.load_userdict(USER_DICT)
else:
    # 可选：开发阶段给个提示，方便发现路径写错
    print(f"[jieba] 未找到自定义词典 {USER_DICT}，仅使用默认词典")

def init_searcher(index_dir: str = "index") -> IndexSearcher:
    """初始化 PyLucene 和 IndexSearcher"""
    try:
        env = lucene.getVMEnv()
    except Exception:
        env = None
    if env is None:
        lucene.initVM(vmargs=["-Djava.awt.headless=true"])

    directory = FSDirectory.open(Paths.get(index_dir))
    reader = DirectoryReader.open(directory)
    searcher = IndexSearcher(reader)
    return searcher

SEARCHER = init_searcher()
ANALYZER = WhitespaceAnalyzer()
QP = QueryParser("content", ANALYZER)


# ========= 2. 加载原始 threebody.json =========

DATA_PATH = "threebody.json"

if not os.path.exists(DATA_PATH):
    raise RuntimeError(f"未找到数据文件: {DATA_PATH}")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    RAW_DOCS: List[Dict[str, Any]] = json.load(f)

DOC_BY_ID: Dict[str, Dict[str, Any]] = {str(d.get("id")): d for d in RAW_DOCS}


# ========= 3. 工具函数：分词 / 分段 / 分句 =========

STOPWORDS = set("""
的 了 在 是 和 有 又 都 把 被 也 很 就 只 但 并 则 而 及 与 或 等 于 上 下 中 吗 呢 啊 吧 呀
""".split())
STOPWORDS.update({"什么", "怎样", "怎么", "如何", "为什么", "为何", "谁"})


def get_query_terms(text: str) -> List[str]:
    """用于句子/段落匹配的查询词：分词 + 去掉部分虚词 + 去掉单字"""
    terms = [t.strip() for t in jieba.lcut(text) if t.strip()]
    filtered = [t for t in terms if (len(t) > 1 and t not in STOPWORDS)]
    # 如果全被过滤掉，就退回到原始 terms，避免完全没有关键词
    return filtered or terms

def tokenize_query(text: str) -> str:
    """和建索引时保持一致：jieba 分词，再空格拼接"""
    tokens = [t for t in jieba.lcut(text) if t.strip()]
    return " ".join(tokens)

def split_paragraphs(raw: str) -> List[str]:
    """简单按空行拆段，可以根据实际文本微调"""
    parts = re.split(r"\n\s*\n+", raw.strip())
    return [p.strip() for p in parts if p.strip()]

def split_sentences(raw: str) -> List[str]:
    """
    简单句子切分：
    - 按中文句号/问号/叹号
    - 以及英文 . ? ! 后面拆分
    """
    text = re.sub(r"\s+", " ", raw)
    parts = re.split(r"(?<=[。！？!?])\s*", text)
    return [s.strip() for s in parts if s.strip()]


# ========= 4. 核心函数：多粒度搜索 =========

def search_multi_granularity(query: str,
                             top_k_chapters: int = 10) -> Dict[str, Any]:
    """
    输入：
      query: 用户查询字符串（中文）
      top_k_chapters: 召回多少个章节

    输出：
      {
        "query": 原始查询,
        "chapters": [
          {
            "doc_id": ...,
            "book": ...,
            "chapter": ...,
            "score": Lucene打分,
            "hit_sentences": [ { "index": i, "text": "句子文本" }, ... ],
            "hit_paragraphs": [ { "index": j, "text": "段落文本" }, ... ],
          },
          ...
        ],
        "sentences": [ 全局句子列表，同样带 doc_id/book/chapter ],
        "paragraphs": [ 全局段落列表，同样带 doc_id/book/chapter ],
      }
    """

    # 1. Lucene 检索章节
    q_str = tokenize_query(query)
    lucene_query = QP.parse(q_str)
    hits = SEARCHER.search(lucene_query, top_k_chapters).scoreDocs

    # 把查询也分词，用于句子/段落匹配
    query_terms = get_query_terms(query)

    # 用一个正则做简单高亮（可选）
    pattern = re.compile("|".join(map(re.escape, query_terms))) if query_terms else None

    chapter_results = []
    sentence_results = []
    paragraph_results = []

    for hit in hits:
        lucene_doc = SEARCHER.doc(hit.doc)
        doc_id = lucene_doc.get("id")
        book = lucene_doc.get("book")
        chapter_title = lucene_doc.get("chapter")
        score = float(hit.score)

        # 2. 找到原始章节内容
        raw_content = ""
        if doc_id in DOC_BY_ID:
            raw_content = DOC_BY_ID[doc_id].get("content", "") or ""

        paragraphs = split_paragraphs(raw_content)
        sentences = split_sentences(raw_content)

        # 3. 找出命中的段落和句子
        hit_paras = []
        hit_sents = []

        for idx, para in enumerate(paragraphs):
            if any(term in para for term in query_terms):
                text = para
                if pattern:
                    text = pattern.sub(lambda m: f"[{m.group(0)}]", text)
                hit_paras.append({"index": idx, "text": text})

        for idx, sent in enumerate(sentences):
            if any(term in sent for term in query_terms):
                text = sent
                if pattern:
                    text = pattern.sub(lambda m: f"[{m.group(0)}]", text)
                hit_sents.append({"index": idx, "text": text})

        # 章节级别条目
        chapter_entry = {
            "doc_id": doc_id,
            "book": book,
            "chapter": chapter_title,
            "score": score,
            "hit_sentences": hit_sents,
            "hit_paragraphs": hit_paras,
        }
        chapter_results.append(chapter_entry)

        # 全局句子/段落列表（方便 UI 做“只看句子”视图）
        for s in hit_sents:
            entry = dict(s)
            entry.update({"doc_id": doc_id, "book": book, "chapter": chapter_title})
            sentence_results.append(entry)

        for p in hit_paras:
            entry = dict(p)
            entry.update({"doc_id": doc_id, "book": book, "chapter": chapter_title})
            paragraph_results.append(entry)

    return {
        "query": query,
        "chapters": chapter_results,
        "sentences": sentence_results,
        "paragraphs": paragraph_results,
    }


# ========= 5. 简单命令行测试 =========

if __name__ == "__main__":
    q = "阶梯计划"  # 或者你想测的任何关键词
    res = search_multi_granularity(q, top_k_chapters=10)

    print("=== 章节级结果 ===")
    for ch in res["chapters"]:
        print(f"[{ch['book']} · {ch['chapter']}] score={ch['score']:.4f}")
        print(f"  命中句子数: {len(ch['hit_sentences'])}  命中段落数: {len(ch['hit_paragraphs'])}")

        # 打印前 2 个命中句子示例
        for s in ch["hit_sentences"][:2]:
            print(f"    句子#{s['index']}: {s['text'][:80]}...")
        # 打印前 1 个命中段落示例
        for p in ch["hit_paragraphs"][:1]:
            print(f"    段落#{p['index']}: {p['text'][:80]}...")

        print()

    print("=== 全局句子命中数:", len(res["sentences"]))
    print("=== 全局段落命中数:", len(res["paragraphs"]))

    from org.apache.lucene.index import Term

    def debug_term(term_text: str):
        reader = SEARCHER.getIndexReader()
        term = Term("content", term_text)
        df = reader.docFreq(term)
        print(f"docFreq('{term_text}') =", df)

    debug_term("歌者")
    debug_term("歌")
    debug_term("者")
