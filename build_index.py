#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构建三体三部曲的 Lucene 索引（用 jieba 分词，与 search.py 保持一致）"""

import os
import json
import re
from collections import defaultdict
import jieba

#1.分词

USER_DICT_PATH = "vocab.txt"
if os.path.exists(USER_DICT_PATH):
    print(f"加载三体自定义词表: {USER_DICT_PATH}")
    with open(USER_DICT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            w = line.split()[0]   # 只要第一个字段
            jieba.add_word(w)
else:
    print(f"未找到三体词表 {USER_DICT_PATH}，跳过自定义词加载")

def jieba_tokenizer(text: str):
    # 和 search.py 保持一致，只做 strip，不再额外正则清洗
    from search import tokenize_query
    return tokenize_query(text).split()


def simple_tokenizer(text: str):
    """简单分词：按非字母数字切分。仅在没有 jieba 时兜底。"""
    text = re.sub(r"[^\w]+", " ", text)
    return [t for t in text.split() if t]


def get_tokenizer():
    return jieba_tokenizer


# 2. PyLucene 初始化 & 建索引

HAS_LUCENE = False
try:
    import lucene

    try:
        env = lucene.getVMEnv()
    except Exception:
        env = None
    if env is None:
        lucene.initVM(vmargs=["-Djava.awt.headless=true"])

    print("PyLucene OK, version =", lucene.VERSION)

    from java.nio.file import Paths
    from org.apache.lucene.store import FSDirectory
    from org.apache.lucene.analysis.core import WhitespaceAnalyzer
    from org.apache.lucene.index import IndexWriter, IndexWriterConfig
    from org.apache.lucene.document import Document, StringField, TextField, StoredField, Field

    HAS_LUCENE = True
except Exception as e:
    print("未能使用 PyLucene，原因：", e)
    HAS_LUCENE = False


def create_lucene_index(json_path: str, index_dir: str = "index"):
    """
    用 PyLucene + jieba 构建索引：
    - 对 content 字段做 jieba 分词，然后用 WhitespaceAnalyzer 建索引
    - id / book / chapter 使用 StringField 存储，content 用 TextField
    """
    with open(json_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    print(f"[Lucene] 读取到 {len(docs)} 条文档")

    directory = FSDirectory.open(Paths.get(index_dir))
    analyzer = WhitespaceAnalyzer()
    config = IndexWriterConfig(analyzer)
    config.setOpenMode(IndexWriterConfig.OpenMode.CREATE)
    writer = IndexWriter(directory, config)

    tokenizer = get_tokenizer()
  

    for i, d in enumerate(docs):
        doc = Document()
        doc_id = str(d.get("id", i))
        book = d.get("book", "") or ""
        chapter = d.get("chapter", "") or ""
        content = d.get("content", "") or ""

        # 基本字段：可存储、可查询
        doc.add(StringField("id",      doc_id,  Field.Store.YES))
        doc.add(StringField("book",    book,    Field.Store.YES))
        doc.add(StringField("chapter", chapter, Field.Store.YES))

        # 章节标题：也可以作为 TextField，便于搜索
        if chapter:
            doc.add(TextField("chapter_text", chapter, Field.Store.YES))

        # 内容分词后用空格拼接，配合 WhitespaceAnalyzer
        tokens = tokenizer(content)
        seg = " ".join(tokens)
        # 注意：这里不再做额外正则清洗，和 search.py 完全同源
        doc.add(TextField("content", seg, Field.Store.NO))   # 索引分词结果，不存储
        doc.add(StoredField("raw_content", content))         # 存储原文

        writer.addDocument(doc)
        if (i + 1) % 10 == 0:
            print(f"[Lucene] 已索引 {i+1} 条文档")

    writer.commit()
    writer.close()
    print(f"[Lucene] 索引构建完成，目录: {index_dir}")


def main():
    json_path = "threebody.json"   # 输入：72 条合并后的三体三部曲章节
    index_dir = "index"            # Lucene 索引目录（与 search.py 相同）

    if not os.path.exists(json_path):
        print("错误：未找到", json_path)
        return

    if HAS_LUCENE:
        print("使用 PyLucene + jieba 构建 Lucene 索引")
        create_lucene_index(json_path, index_dir)
    else:
        print("PyLucene 不可用，跳过索引构建")

if __name__ == "__main__":
    main()

