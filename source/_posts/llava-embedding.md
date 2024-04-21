---
title: llava-embedding
tags: report, ASPIRE
category:
  - report
presentation:
  width: 1920
  height: 1080
date: 2024-03-31 22:30:01
---
<!-- slide -->
## 本周完成事项
* 初步了解了llava的组成部分和代码结构
  * 在服务器部署了llava-1.5-7b-hf
  * 拆分出embedding部分
* 初步测试 malicious text & benign text v.s. adversarial image(熊猫) 的 cosine similarity
  * 文本部分采用在MMLU和harmbench各40个text input
  * 发现两者表现出一定的差异(如下图)

![embeddings](analysis2.png) ![analysis](different-pic-result.png)
左图：直方图展示两类text与img-16的cosine similarity分布; 以及类别内均值和标准差
右图：展示 两类文本v.s.五张图片的cosine similarity；其中红线表达两者**均值之差**的变化趋势

<!-- slide -->
## 下周计划
* 部署denoiser
* 分析denoise后图像与text的cosine similarity变化情况