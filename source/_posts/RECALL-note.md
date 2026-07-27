---
title: RECALL-note
date: 2024-12-30 10:36:18
tags:
- RAG
- RECALL
- note
---

# 论文笔记 RECALL: A Benchmark for LLMs Robustness against External Counterfactual Knowledge

## 要点概括
目的：to evaluate the ability of LLMs to discern the reliability of external knowledge

### Introduction
we expect them to **generate trustworthy responses** to user queries regardless of the quality of given information. In other words, we hope to assess the **robustness of LLMs against external counterfactual knowledge** in order to generate the right answers for user inputs.
create a benchmark **from existing datasets** by** adding counterfactual information** into original samples through ChatGPT
two **existing methods fail** to effectively alleviate the problem

### Benchmark Construction
作者的一些假设：
1. 外部知识是从互联网上搜索得到的，因此会含有不实信息
2. 理论上模型无法分辨不实信息，所以关注外部（不实）信息与内部知识冲突的情况
3. 有两种主要的提问方式
   1. seeks for certain specific attributes of an entity or event like the winner of a football game or the reasons for a phenomenon
   2. hopes to get a brief description about an object like an introduction to a physical term.
   因此他们设置了QA和Text Generation两类任务，同时考虑QA问题中不实信息的位置，也分为两种
   1. QA-A: 文档中问题的答案是错误的
   2. QA-NA: 文档中答案正确但有其他事实错误

| tasks      | QA                         | Text Generation                      |
| ---------- | -------------------------- | ------------------------------------ |
| Dataset    | EventKG                    | UJ                                   |
| preprocess | structured data->paragraph | 5 non-overlap sentences              |
|            | 提供正确和错误选项二选一   | 根据提供的信息用一句话概括对象的定义 |

### Experiment

3 scenarios:

1. 提供正确doc
2. 提供更改过（错误）的doc
3. 不提供doc

![image-20241230115130734](image-20241230115130734.png)

#### Metrix

对于QA：使用ACC和M-Rate

> **M-Rate** is the proportion of the queries that the model answers wrongly with edited contexts in all queries that the model can answer correctly without external knowledge.

对于生成：

- 使用BLEU，ROUGE-L评估生成质量
- 使用R-Rate评估鲁棒性（proportion of edited words appearing in the model’s outputs in all edited words.（in EventKG））

#### 结果分析
