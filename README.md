# 基于lucene的意图识别与多粒度《三体》搜索引擎

## 写给同志们

同志们，三体垂直搜索引擎来了！

目前非常简陋，但主不在乎。

不要回答！不要回答！

来了，爱了，给了你一串代码，走了。

<img width="2483" height="1199" alt="image" src="https://github.com/user-attachments/assets/fdbbc462-643e-47f2-be2a-ec04bc68e9a7" />

## 安装与运行

主要依赖包：
- Flask==3.0.3
- PyLucene==9.12.0
- jieba==0.42.1
- zhipuai==2.1.5.20230904
- requests==2.31.0

### 1.配置 API Key

编辑 `llm.py`，设置API Key：

```python
client = ZhipuAI(api_key="your-api-key-here")
```

### 2. 构建搜索索引

```bash
python process.py
```
处理三体原文threebody.txt，得到以章节chapter为单位的json文件threebody.json，便于后续建立索引

```bash
python build_index.py
```

此步骤将：
- 读取 `threebody.json` 中的三体三部曲内容
- 使用 jieba 分词（对于vocab中的三体特殊词汇，可能不完全，可以继续更新） + WhitespaceAnalyzer 创建 Lucene 索引
- 生成 `index/` 目录用于搜索

### 3. 运行应用

```bash
python app.py
```

## 检索思路
检索思路：先让llm理解查询（这里设计了一下提示词），把查询分为”原文片段“、”关键词“、”问题“三种类型，把用户的意图分为”定位原文的位置“，”找到小说的具体内容“，”询问一些概念“，”介绍人物”，“了解情节”，然后整理从前端的query，保留核心词送给搜索引擎lucene，lucene先进行召回，然后用python设计规则对召回内容进行打分，返回得分高的句子和章节

## 目前的问题与进一步思路
目前搜索还不够智能，对于一些问题llm回答模糊不清甚至回答错误。

没关系的，都一样。

进一步改进的思路：

1.点击相应的句子，跳转到句子所在的原文

2.加速，检索与llm回答解耦

3.进一步调整llm的提示词/加入工具或知识库

4.完善特殊词vocab.txt
