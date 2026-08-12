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
cleaning_status: draft
review_status: pending
---

# 无监督与集成学习：聚类模型

> 来源：Open Machine Learning Book；许可证：CC-BY-4.0；固定版本：b1a5645749b1e3ec9977693b01c662014b71cae5。

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
