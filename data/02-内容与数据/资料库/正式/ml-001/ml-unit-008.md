---
content_unit_id: ml-unit-008
book_id: ml-001
topic_id: ml-core-001
chapter: 分类与评估
knowledge_points: [ml-classification]
source_id: src-ocademy-ml
source_relative_path: open-machine-learning-jupyter-book/ml-fundamentals/classification/getting-started-with-classification.ipynb
source_commit: b1a5645749b1e3ec9977693b01c662014b71cae5
license: CC-BY-4.0
source_url: https://press.ocademy.cc/ml-fundamentals/classification/getting-started-with-classification.html
attribution: Open Machine Learning Book — Ocademy community
cleaning_status: approved
review_status: approved
reviewer: content-editorial-v1
reviewed_at: 2026-07-31
review_method: editorial-structure-and-source-audit-v1
---

# 分类与评估：分类入门

> 本单元依据 Open Machine Learning Book 的固定版本整理；阅读原文、插图与延伸练习请使用页面中的官方章节链接。

## 学习目标

完成本节后，你应能解释并应用：分类问题。

## 阅读重点

理解离散类别预测及其评价

## 主动回忆检查

不查看资料，尝试用自己的话回答：本节概念解决什么问题？它与前置知识或下一步任务有什么关系？若无法回答，请先完成章节练习，再进行正式复测。

## 原文学习材料

```python
# Install the necessary dependencies

import os
import sys 
!{sys.executable} -m pip install --quiet pandas scikit-learn numpy matplotlib jupyterlab_myst ipython
```

# Getting started with classification

In Asia and India, food traditions are extremely diverse, and very delicious! Let's look at data about regional cuisines to try to understand their ingredients.

> Photo by <a href="https://unsplash.com/@changlisheng?utm_source=unsplash&utm_medium=referral&utm_content=creditCopyText">Lisheng Chang</a> on <a href="https://unsplash.com/s/photos/asian-food?utm_source=unsplash&utm_medium=referral&utm_content=creditCopyText">Unsplash</a>

In this section, you will build on your earlier study of Regression and learn about other classifiers that you can use to better understand the data.

```{tableofcontents}
```

---

> 编辑说明：本稿完成来源、许可证、文本结构、危险嵌入、知识点映射和部署可读性检查；学科正确性与教学难度仍应由课程负责人抽检后持续迭代。
