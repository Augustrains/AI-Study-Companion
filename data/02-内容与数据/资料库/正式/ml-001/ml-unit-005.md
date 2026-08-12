---
content_unit_id: ml-unit-005
book_id: ml-001
topic_id: ml-core-001
chapter: 回归与优化
knowledge_points: [ml-logistic-regression]
source_id: src-ocademy-ml
source_relative_path: open-machine-learning-jupyter-book/ml-fundamentals/regression/logistic-regression.ipynb
source_commit: b1a5645749b1e3ec9977693b01c662014b71cae5
license: CC-BY-4.0
source_url: https://press.ocademy.cc/ml-fundamentals/regression/logistic-regression.html
attribution: Open Machine Learning Book — Ocademy community
cleaning_status: approved
review_status: approved
reviewer: content-editorial-v1
reviewed_at: 2026-07-31
review_method: editorial-structure-and-source-audit-v1
---

# 回归与优化：逻辑回归

> 本单元依据 Open Machine Learning Book 的固定版本整理；阅读原文、插图与延伸练习请使用页面中的官方章节链接。

## 学习目标

完成本节后，你应能解释并应用：逻辑回归。

## 阅读重点

理解二分类概率模型

## 主动回忆检查

不查看资料，尝试用自己的话回答：本节概念解决什么问题？它与前置知识或下一步任务有什么关系？若无法回答，请先完成章节练习，再进行正式复测。

## 原文学习材料

```python
# Install the necessary dependencies

import os
import sys
!{sys.executable} -m pip install --quiet pandas scikit-learn numpy matplotlib jupyterlab_myst ipython seaborn
```

# Logistic regression

A demo of logistic-regression. <a href="https://mlu-explain.github.io/logistic-regression/"> [source]</a >

## Introduction

In this final section on Regression, one of the basic _classic_ Machine Learning techniques, we will take a look at Logistic Regression. You would use this technique to discover patterns to predict binary categories. Is this candy chocolate or not? Is this disease contagious or not? Will this customer choose this product or not?

In this section, you will learn:

- A new library for data visualization
- Techniques for logistic regression

## Prerequisite

Having worked with the pumpkin data, we are now familiar enough with it to realize that there's one binary category that we can work with: `Color`.

Let's build a logistic regression model to predict that, given some variables, _what color a given pumpkin is likely to be_ (orange 🎃 or white 👻).

## Define the question

For our purposes, we will express this as a binary: 'Orange' or 'Not Orange'. There is also a 'striped' category in our dataset but there are few instances of it, so we will not use it. It disappears once we remove null values from the dataset, anyway.

## About logistic regression

Logistic regression differs from linear regression, which you learned about previously, in a few important ways.

### Binary classification

Logistic regression does not offer the same features as linear regression. The former offers a prediction about a binary category ("orange or not orange") whereas the latter is capable of predicting continual values, for example given the origin of a pumpkin and the time of harvest, _how much its price will rise_.

### Other classifications

There are other types of logistic regression, including multinomial and ordinal:

- **Multinomial**, which involves having more than one category - "Orange, White, and Striped".
- **Ordinal**, which involves ordered categories, useful if we wanted to order our outcomes logically, like our pumpkins that are ordered by a finite number of sizes (mini, sm, med, lg, xl, xxl).

### It's still linear

Even though this type of Regression is all about 'category predictions', it still works best when there is a clear linear relationship between the dependent variable (color) and the other independent variables (the rest of the dataset, like city name and size). It's good to get an idea of whether there is any linearity dividing these variables or not.

### Variables DO NOT have to correlate

Remember how linear regression worked better with more correlated variables? Logistic regression is the opposite - the variables don't have to align. That works for this data which has somewhat weak correlations.

### You need a lot of clean data

Logistic regression will give more accurate results if you use more data; our small dataset is not optimal for this task, so keep that in mind.

## Exercise - tidy the data

First, clean the data a bit, dropping null values and selecting only some of the columns:

1. Add the following code:

```python
import pandas as pd
import numpy as np

pumpkins = pd.read_csv('https://static-1300131294.cos.ap-shanghai.myqcloud.com/data/us-pumpkins.csv')
pumpkins.head()
```

```python
from sklearn.preprocessing import LabelEncoder

new_columns = ['Color','Origin','Item Size','Variety','City Name','Package']

new_pumpkins = pumpkins.drop([c for c in pumpkins.columns if c not in new_columns], axis=1)

new_pumpkins.dropna(inplace=True)

new_pumpkins = new_pumpkins.apply(LabelEncoder().fit_transform)
```

You can always take a peek at your new dataframe:

```python
new_pumpkins.info
```

### Visualization - side-by-side grid

By now you have loaded up the starter notebook（请通过本页“官方章节”链接查看） with pumpkin data once again and cleaned it so as to preserve a dataset containing a few variables, including `Color`. Let's visualize the dataframe in the notebook using a different library: [Seaborn](https://seaborn.pydata.org/index.html), which is built on Matplotlib which we used earlier.

Seaborn offers some neat ways to visualize your data. For example, you can compare distributions of the data for each point in a side-by-side grid.

1. Create such a grid by instantiating a `PairGrid`, using our pumpkin data `new_pumpkins`, followed by calling `map()`:

```python
import seaborn as sns

g = sns.PairGrid(new_pumpkins)
g.map(sns.scatterplot)
```

By observing data side-by-side, you can see how the Color data relates to the other columns.

### Use a swarm plot

Since Color is a binary category (Orange or Not), it's called 'categorical data' and needs 'a more [specialized approach](https://seaborn.pydata.org/tutorial/categorical.html?highlight=bar) to visualization'. There are other ways to visualize the relationship of this category with other variables. 

You can visualize variables side-by-side with Seaborn plots.

1. Try a 'swarm' plot to show the distribution of values:

```python
sns.swarmplot(x="Color", y="Item Size", data=new_pumpkins)
```

### Violin plot

A 'violin' type plot is useful as you can easily visualize the way that data in the two categories is distributed. Violin plots don't work so well with smaller datasets as the distribution is displayed more 'smoothly'.

1. As parameters `x=Color`, `kind="violin"` and call `catplot()`:

```python
sns.catplot(x="Color", y="Item Size",
            kind="violin", data=new_pumpkins)
```

Now that we have an idea of the relationship between the binary categories of color and the larger group of sizes, let's explore logistic regression to determine a given pumpkin's likely color.

Where the sigmoid's midpoint finds itself at x's $0$ point, L is the curve's maximum value, and $k$ is the curve's steepness. If the outcome of the function is more than 0.5, the label in question will be given the class '1' of the binary choice. If not, it will be classified as '0'.

:::

## Build your model

Building a model to find these binary classification is surprisingly straightforward in Scikit-learn.

1 . Select the variables you want to use in your classification model and split the training and test sets calling `train_test_split()`:

```python
from sklearn.model_selection import train_test_split

Selected_features = ['Origin','Item Size','Variety','City Name','Package']

X = new_pumpkins[Selected_features]
y = new_pumpkins['Color']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=0)
```

2 . Now you can train your model, by calling `fit()` with your training data, and print out its result:

```python
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report 
from sklearn.linear_model import LogisticRegression

model = LogisticRegression()
model.fit(X_train, y_train)
predictions = model.predict(X_test)

print(classification_report(y_test, predictions))
print('Predicted labels: ', predictions)
print('Accuracy: ', accuracy_score(y_test, predictions))
```

## Better comprehension via a confusion matrix

While you can get a scoreboard report [terms](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.classification_report.html?highlight=classification_report#sklearn.metrics.classification_report) by printing out the items above, you might be able to understand your model more easily by using a [confusion matrix](https://scikit-learn.org/stable/modules/model_evaluation.html#confusion-matrix) to help us understand how the model is performing.

1. To use a confusion metrics, call `confusion_matrix()`:

```python
from sklearn.metrics import confusion_matrix
confusion_matrix(y_test, predictions)
```

Take a look at your model's confusion matrix:
:::output
array([[162,   4],
        [ 33,   0]])
:::

In Scikit-learn, confusion matrices Rows (axis 0) are actual labels and columns (axis 1) are predicted labels.

What's going on here? Let's say our model is asked to classify pumpkins between two binary categories, category 'orange' and category 'not-orange'.

- If your model predicts a pumpkin as not orange and it belongs to category 'not-orange' in reality we call it a true negative, shown by the top left number.
- If your model predicts a pumpkin as orange and it belongs to category 'not-orange' in reality we call it a false negative, shown by the bottom left number.
- If your model predicts a pumpkin as not orange and it belongs to category 'orange' in reality we call it a false positive, shown by the top right number.
- If your model predicts a pumpkin as orange and it belongs to category 'orange' in reality we call it a true positive, shown by the bottom right number.

As you might have guessed it's preferable to have a larger number of true positives and true negatives and a lower number of false positives and false negatives, which implies that the model performs better.

How does the confusion matrix relate to precision and recall? Remember, the classification report printed above showed precision (0.83) and recall (0.98).

$$
Precision = \frac{tp}{tp + fp} = \frac{162}{162 + 33} = 0.8307692307692308

Recall = \frac{tp}{tp + fn} = \frac{162}{162 + 4} = 0.9759036144578314
$$

Let's revisit the terms we saw earlier with the help of the confusion matrix's mapping of $\frac{TP}{TN}$ and $\frac{FP}{FN}$ :

🎓 Precision: $\frac{TP}{TP + FP}$ The fraction of relevant instances among the retrieved instances (e.g. which labels were well-labeled)

🎓 Recall: $\frac{TP}{TP + FN}$ The fraction of relevant instances that were retrieved, whether well-labeled or not

🎓 f1-score: $\frac{2 * precision * recall}{precision + recall}$ A weighted average of the precision and recall, with best being 1 and worst being 0

🎓 Support: The number of occurrences of each label retrieved

🎓 Accuracy: $\frac{TP + TN}{TP + TN + FP + FN}$ The percentage of labels predicted accurately for a sample.

🎓 Macro Avg: The calculation of the unweighted mean metrics for each label, not taking label imbalance into account.

🎓 Weighted Avg: The calculation of the mean metrics for each label, taking label imbalance into account by weighting them by their support (the number of true instances for each label).

## Visualize the ROC curve of this model

This is not a bad model; its accuracy is in the 80% range so ideally you could use it to predict the color of a pumpkin given a set of variables.

Let's do one more visualization to see the so-called 'ROC' score:

```python
from sklearn.metrics import roc_curve, roc_auc_score

y_scores = model.predict_proba(X_test)
# calculate ROC curve
fpr, tpr, thresholds = roc_curve(y_test, y_scores[:, 1])
sns.lineplot(x=[0, 1], y=[0, 1])
sns.lineplot(x=fpr, y=tpr)
```

Using Seaborn again, plot the model's [Receiving Operating Characteristic](https://scikit-learn.org/stable/auto_examples/model_selection/plot_roc.html?highlight=roc) or ROC. ROC curves are often used to get a view of the output of a classifier in terms of its true vs. false positives. "ROC curves typically feature true positive rate on the Y axis, and false positive rate on the X axis." Thus, the steepness of the curve and the space between the midpoint line and the curve matter: you want a curve that quickly heads up and over the line. In our case, there are false positives to start with, and then the line heads up and over properly:

Finally, use Scikit-learn's [`roc_auc_score` API](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_auc_score.html?highlight=roc_auc#sklearn.metrics.roc_auc_score) to compute the actual 'Area Under the Curve' (AUC):

```python
auc = roc_auc_score(y_test,y_scores[:, 1])
print(auc)
```

The result is `0.6976998904709748`. Given that the AUC ranges from 0 to 1, you want a big score, since a model that is 100% correct in its predictions will have an AUC of 1; in this case, the model is _pretty good_.

In future lessons on classifications, you will learn how to iterate to improve your model's scores. But for now, congratulations! You've completed these regression sections!

## Your turn! 🚀

There's a lot more to unpack regarding logistic regression! But the best way to learn is to experiment. Find a dataset that lends itself to this type of analysis and build a model with it. What do you learn? tip: try [Kaggle](https://www.kaggle.com/search?q=logistic+regression+datasets) for interesting datasets.

Assignment - Retrying some regression（请通过本页“官方章节”链接查看）

## Self study

Read the first few pages of [this paper from Stanford](https://web.stanford.edu/~jurafsky/slp3/5.pdf) on some practical uses for logistic regression. Think about tasks that are better suited for one or the other type of regression tasks that we have studied up to this point. What would work best?

## Acknowledgments

Thanks to Microsoft for creating the open-source course [ML-For-Beginners](https://github.com/microsoft/ML-For-Beginners). It inspires the majority of the content in this chapter.

---

> 编辑说明：本稿完成来源、许可证、文本结构、危险嵌入、知识点映射和部署可读性检查；学科正确性与教学难度仍应由课程负责人抽检后持续迭代。
