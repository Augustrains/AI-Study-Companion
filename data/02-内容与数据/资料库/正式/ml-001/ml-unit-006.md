---
content_unit_id: ml-unit-006
book_id: ml-001
topic_id: ml-core-001
chapter: 回归与优化
knowledge_points: [ml-loss-function]
source_id: src-ocademy-ml
source_relative_path: open-machine-learning-jupyter-book/ml-fundamentals/parameter-optimization/loss-function.ipynb
source_commit: b1a5645749b1e3ec9977693b01c662014b71cae5
license: CC-BY-4.0
source_url: https://press.ocademy.cc/ml-fundamentals/parameter-optimization/loss-function.html
attribution: Open Machine Learning Book — Ocademy community
cleaning_status: approved
review_status: approved
reviewer: content-editorial-v1
reviewed_at: 2026-07-31
review_method: editorial-structure-and-source-audit-v1
---

# 回归与优化：损失函数

> 本单元依据 Open Machine Learning Book 的固定版本整理；阅读原文、插图与延伸练习请使用页面中的官方章节链接。

## 学习目标

完成本节后，你应能解释并应用：损失函数。

## 阅读重点

理解学习目标如何被量化

## 主动回忆检查

不查看资料，尝试用自己的话回答：本节概念解决什么问题？它与前置知识或下一步任务有什么关系？若无法回答，请先完成章节练习，再进行正式复测。

## 原文学习材料

```python
# Install the necessary dependencies

import sys
import os
!{sys.executable} -m pip install --quiet pandas numpy matplotlib jupyterlab_myst ipython
```

# Loss function

The function we want to minimize or maximize is called the objective function or criterion. When we are minimizing it, we may also call it the cost function, loss function, or error function.

— Deep Learning, Ian Goodfellow, Yoshua Bengio, Aaron Courville

## Objective of this section

We have already learned math and code for "Gradient Descent", as well as other optimization techniques.

In this section, we will learn more about loss functions for Linear Regression and Logistic Regression.

## What’s the Difference between a Loss Function and a Cost Function?

A loss function is for a single training example. It is also sometimes called an error function. A cost function, on the other hand, is the average loss over the entire training dataset. The optimization strategies aim at minimizing the cost function.

## Regression Loss Functions

### Squared Error Loss

Squared Error loss for each training example, 
also known as **L2 Loss**, is the square of the 
difference between the actual and the predicted values:

$$L = (y - f(x))^2$$

The corresponding cost function is the 
Mean of these Squared Errors (MSE).

### Absolute Error Loss

Absolute Error for each training example 
is the distance between the predicted and the actual values, 
irrespective of the sign. Absolute Error is also 
known as the **L1 loss**:

$$L = \lvert y - f(x) \rvert$$

The corresponding cost function is the Mean of these Absolute Errors (MAE).

## Classification Loss Functions

### Binary Cross Entropy Loss

Cross-entropy is the default loss function to use for binary classification problems.

It is intended for use with binary classification where the target values are in the set {0, 1}.

Mathematically, it is the preferred loss function 
under the inference framework of maximum likelihood. 
It is the loss function to be evaluated first and only 
changed if you have a good reason.

Cross-entropy will calculate a score that summarizes 
the average difference between the actual and predicted 
probability distributions for predicting class 1. 
The score is minimized and a perfect cross-entropy value is 0.

This YouTube video by Andrew Ng explains very well Binary Cross Entropy Loss (make sure 
that you have access to YouTube for this web page to render correctly):

```python
from IPython.display import HTML

display(
    HTML(
        """

video. <a href="https://www.youtube.com/embed/SHEPb1JHw5o">[source]</a>

"""
    )
)
```

### Multi-Class Cross-Entropy Loss

Cross-entropy is the default loss function to 
use for multi-class classification problems.

In this case, it is intended for use with 
multi-class classification where the target values 
are in the set {0, 1, 3, …, n}, where each class is 
assigned a unique integer value.

Mathematically, it is the preferred loss 
function under the inference framework of 
maximum likelihood. It is the loss function 
to be evaluated first and only changed if you have a good reason.

Cross-entropy will calculate a score that 
summarizes the average difference between 
the actual and predicted probability distributions 
for all classes in the problem. The score is minimized 
and a perfect cross-entropy value is 0.

##  [optional] At the frontier of Machine Learning Research

```python
from IPython.display import HTML

display(
    HTML(
        """

video. <a href="https://www.youtube.com/embed/QBbC3Cjsnjg">[source]</a>

"""
    )
)
```

With its corresponding paper: [A General and Adaptive Robust Loss Function](https://arxiv.org/abs/1701.03077)

## Bibliography

- [ML cheat sheet for loss functions](https://ml-cheatsheet.readthedocs.io/en/latest/loss_functions.html)
- [A Short Introduction to Entropy, Cross-Entropy and KL-Divergence](https://www.youtube.com/watch?v=ErfnhcEV1O8)

## Your turn! 🚀
 
Please complete the following tasks:
loss-function（请通过本页“官方章节”链接查看）

---

> 编辑说明：本稿完成来源、许可证、文本结构、危险嵌入、知识点映射和部署可读性检查；学科正确性与教学难度仍应由课程负责人抽检后持续迭代。
