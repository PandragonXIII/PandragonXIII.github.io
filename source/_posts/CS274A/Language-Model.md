---
title: CS274A-Language Model
date: 2024-03-14 08:28:07
tags: note NLP
math: true
category:
- note
- CS274A
---



# Language Model

相对于分类、生成等任务中将语言看作 **词的集合或向量**， 语言模型中将文本作为 **词的序列** 



通过估计条件概率进行预测

* n-gram: 只考虑前面n个单词的影响（作为概率的条件）
* RNN
* Transformer：将一些上文需要关注的单词作为条件（注意力机制）
* ？



### LM的特殊处理

##### unknown word

构建token `<UNK>`, 

1. 构建词表
2. 检索训练文本中不在词表中的词
   1. 较多的词添加到词表
   2. 较少的词换成`<UNK>`
3. 正常训练

也可以从字符/sub word 层面构建语言模型，避免生词出现



### LM的评估

Extrinsic: 针对下游任务，同前

Intrinsic: 

#### Perplexity

困惑度：LM应该对没见过的真实句子给出较高的分数

For test data $\bar x_{1:m}$ (m sentences):

average log-probability per word of $\bar x_{1:m}$ is
$$
l=-\frac1M\sum_{i=1}^m\log_2p(\bar x_i)
$$
if $M=\sum_{i=1}^m|\bar x_i|$ 



perplexity= $2^l$ 

> 在信息论中表达了编码所需的最小bit数

即希望用尽量少的词得到概率尽量大的一系列词（来对信息进行编码）

例

* 如果训练数据概率为1，困惑度=1
* 如果=0，困惑度=$\infty$ 

==注意==: 困惑度受词表影响

---



## N-gram Model

如果n=1，为Unigram model，即每个单词相互独立

用MLE，概率=序列出现次数/序列前n出现次数

问题：数据稀疏

利用平滑

#### Back-off

如果当前n-gram的效果不好，那么就用n+1gram



#### Interpolation

线性插值

将不同n值的n-gram分别估算概率然后加权平均



### 生成式

Auto-aggressive generate

语法通顺但语义不行(incoherent)。



> fixed-window neural LM
>
> n-gram的神经网络实现：将词向量连接后过线性变换和激活函数
>
> 用神经网络记住参数，不用对所有组合记录概率
>
> 同时由于同类词语可能具有类似的embedding，泛化能力更好（神经网络是平滑的，类似的输入带来类似的输出）

## RNN

每一个时刻的新隐向量都根据上一个时刻的隐向量和新的word embedding得到

#### 学习

MLE

计算真实分布$y^{(t)}$和 $\hat y^{(t)}$的cross entropy 作为loss（真实分布是one-hot的）

等同于最大化所有位置正确单词的概率



**问题**：梯度消失/梯度爆炸

梯度爆炸导致更新步长过大；解决方案：gradient clipping：梯度大于阈值时设置为上限值



### LSTM



## Attention

对每一个state相对于当前state计算一个attention score，用其值做加权平均得到一个综合的新state，包含更多需要注意的state



#### masking

对于将来的词（不应该被看到），将attention score设为$-\infty$ 



### Multi-head attention

将key-value-query 线性映射到不同空间，得到多种注意力



对过长的输入也只关心一定长度内的历史



### 在Transformer上的attention

利用positioning embedding保留词的位置信息；

- 问题：词的含义可能与位置无关；长度外推性（不能处理没见过的绝对长度）

**相对位置编码**：即两个词之间的长度，有上界k

加在key和value上



##### RoPE

旋转位置编码



对于多层的self-attention 网络，多次线性变换其实可以用一次线性变换代替，因此没有意义

所以引入非线性：在每层做完 attention 后过两层神经网络 (feed-forward)

> 一般是先升维再降维（4倍）

> Feed-forward层也可以被解释为某种全局的attention/ global memory



**残差connection**

提供跨国多层保留信息的渠道，函数更平衡

$x_{n+1}=F(x)+x$ 



**Layer Normalization**

算完self-attention/feed forward 后进行标准化，避免前面层输出变化影响后面已经训练好的参数



#### Complexity

$(QK^T)V$ -> $O(T^2d_k)$ 

1. sparse attention:只关注开头和最近的部分token
2. Linear attention: 去掉（用核函数近似）softmax后 用交换律达到 $O(Td_k^2)$ 



