---
content_unit_id: ml-unit-009
book_id: ml-001
topic_id: ml-core-001
chapter: 无监督与集成学习
knowledge_points: [ml-clustering]
source_id: src-ocademy-ml
source_relative_path: open-machine-learning-jupyter-book/ml-advanced/clustering/clustering-models-for-machine-learning.ipynb
source_commit: b1a5645749b1e3ec9977693b01c662014b71cae5
license: CC-BY-4.0
source_url: https://press.ocademy.cc/ml-advanced/clustering/clustering-models-for-machine-learning.html
attribution: Open Machine Learning Book — Ocademy community
cleaning_status: approved
review_status: approved
reviewer: content-editorial-v1
reviewed_at: 2026-07-31
review_method: editorial-structure-and-source-audit-v1
---

# 无监督与集成学习：聚类模型

> 本单元依据 Open Machine Learning Book 的固定版本整理；阅读原文、插图与延伸练习请使用页面中的官方章节链接。

## 学习目标

完成本节后，你应能解释并应用：聚类。

## 阅读重点

理解无标签数据的分组方法

## 主动回忆检查

不查看资料，尝试用自己的话回答：本节概念解决什么问题？它与前置知识或下一步任务有什么关系？若无法回答，请先完成章节练习，再进行正式复测。

## 原文学习材料

```python
# Install the necessary dependencies

import os
import sys
!{sys.executable} -m pip install --quiet pandas scikit-learn numpy matplotlib jupyterlab_myst ipython
```

# Clustering models for Machine Learning

Clustering is a machine learning task where it looks to find objects that resemble one another and group these into groups called clusters.  What differs clustering from other approaches in machine learning, is that things happen automatically, in fact, it's fair to say it's the opposite of supervised learning. 

Nigeria's diverse audience has diverse musical tastes, let's look at some music popular in Nigeria. This dataset includes data about various songs' 'danceability' score, 'acousticness', loudness, 'speechiness', popularity and energy. It will be interesting to discover patterns in this data!

```{tableofcontents}
```

---

> 编辑说明：本稿完成来源、许可证、文本结构、危险嵌入、知识点映射和部署可读性检查；学科正确性与教学难度仍应由课程负责人抽检后持续迭代。
