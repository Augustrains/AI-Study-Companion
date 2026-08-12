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
cleaning_status: draft
review_status: pending
---

# 分类与评估：分类入门

> 来源：Open Machine Learning Book；许可证：CC-BY-4.0；固定版本：b1a5645749b1e3ec9977693b01c662014b71cae5。

```python
# Install the necessary dependencies

import os
import sys 
!{sys.executable} -m pip install --quiet pandas scikit-learn numpy matplotlib jupyterlab_myst ipython
```

# Getting started with classification

In Asia and India, food traditions are extremely diverse, and very delicious! Let's look at data about regional cuisines to try to understand their ingredients.

![Thai food seller](https://static-1300131294.cos.ap-shanghai.myqcloud.com/images/ml-fundamentals/ml-classification/thai-food.jpg)
> Photo by <a href="https://unsplash.com/@changlisheng?utm_source=unsplash&utm_medium=referral&utm_content=creditCopyText">Lisheng Chang</a> on <a href="https://unsplash.com/s/photos/asian-food?utm_source=unsplash&utm_medium=referral&utm_content=creditCopyText">Unsplash</a>

In this section, you will build on your earlier study of Regression and learn about other classifiers that you can use to better understand the data.

```{tableofcontents}
```
