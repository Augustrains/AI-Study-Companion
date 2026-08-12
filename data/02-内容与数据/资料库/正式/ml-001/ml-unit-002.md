---
content_unit_id: ml-unit-002
book_id: ml-001
topic_id: ml-core-001
chapter: 机器学习基础与监督学习
knowledge_points: [ml-learning-paradigm]
source_id: src-ocademy-ml
source_relative_path: open-machine-learning-jupyter-book/ml-fundamentals/ml-summary.ipynb
source_commit: b1a5645749b1e3ec9977693b01c662014b71cae5
license: CC-BY-4.0
source_url: https://press.ocademy.cc/ml-fundamentals/ml-summary.html
attribution: Open Machine Learning Book — Ocademy community
cleaning_status: approved
review_status: approved
reviewer: content-editorial-v1
reviewed_at: 2026-07-31
review_method: editorial-structure-and-source-audit-v1
---

# 机器学习基础与监督学习：机器学习技术与任务

> 本单元依据 Open Machine Learning Book 的固定版本整理；阅读原文、插图与延伸练习请使用页面中的官方章节链接。

## 学习目标

完成本节后，你应能解释并应用：学习范式。

## 阅读重点

理解模型通过数据改进任务表现的基本范式

## 主动回忆检查

不查看资料，尝试用自己的话回答：本节概念解决什么问题？它与前置知识或下一步任务有什么关系？若无法回答，请先完成章节练习，再进行正式复测。

## 原文学习材料

# Summary of machine learning fundamentals

## Discriminative Models and Generative Models 

### Machine Learning Landscape : Discriminative Models

Most of supervised machine learning can be looked at using the following framework: 
You have a set of training points $(x_i, y_i)$, and you want to find a function f that "fits the data well", 
that is, $yi \approx f(x_i)$ for most $i$.

You will start by doing the following:

- Define the form of $f$. For instance, we can define $f = wx + b$, for some constants $w$ and $b$. 
Note that this is a set of functions — for different values of $w$ and $b$, 
you will get different functions $f$, and you want to find an $f$
from this set that does the “best”.
- As you might have noticed, we have been talking about this notion of “best”, 
which is ill-defined up to this point. So, we need to make this more concrete. 
The goal here, as stated above, is to have $y_i \approx f(x_i)$
for most $i$.

The above two steps essentially define the **function class** and the **loss function** respectively.

Depending on how you choose your function class and the loss function, 
you get different supervised learning models or even unsupervised learning models:

- Linear function class with squared-error loss function — Linear regression
- Linear function class with logistic loss function — Logistic regression
- Linear function class with hinge loss — SVM
- Function class containing a network of neurons with cross-entropy loss — Neural networks

and so on.

### Machine Learning Landscape : Generative Models 

Generative models attempt to capture the overall distribution characteristics of data, including the relationships between variables. These models can generate new data instances that are statistically similar to the original data. Many generative models learn a latent space that represents complex data structures in a more concise form than the original data space.

In generative models, **Defining the Model Structure** involves choosing a model that can represent or approximate the data generation process. Unlike a direct mapping from input to output, this model aims to capture the entire distribution of data. For example, 
- Variational Autoencoders (VAEs) learn the high-dimensional distribution of data through a latent space. 
- Generative Adversarial Networks (GANs) generate realistic data samples through an adversarial process.

**Defining the Loss Function** tends to be more complex in generative models than in supervised learning, as the goal is not just to minimize prediction error. For instance, 
- GANs use an adversarial loss, where the generator aims to maximize the misjudgment rate of the discriminator, which tries to distinguish between real and generated samples. 
- In VAEs, the loss function includes a reconstruction error (to make generated samples as close to real data as possible) and regularization of the latent space.

Depending on the amount of data and model usage you choose, here are some generative models:
- Gaussian Mixture Models (GMM): Models the overall distribution of data by combining multiple Gaussian distributions, commonly used for clustering and density estimation.
- Hidden Markov Models (HMM): Describes sequence data with hidden states, where each state depends on the previous one, suitable for speech recognition and natural language processing.
- Generative Adversarial Networks (GANs): Consists of two parts: a generator that creates data and a discriminator that evaluates its authenticity, mainly used for generating realistic images and videos.
- Variational Autoencoders (VAEs): Combines encoders and decoders to learn the latent representation of data, used for image generation and feature learning.
- Naive Bayes Classifiers: Based on Bayes' theorem and assumes independence among features, commonly used for text classification and spam detection.

### Comparison with Discriminative Models

Generative models focus on modeling while discriminative models focus on solutions. Thus, we can use generative algorithms to generate new data points. Discriminative algorithms cannot serve this purpose. Discriminative algorithms usually perform better in classification tasks. And the real strength of generative algorithms is their ability to express complex relationships between variables.

Generative algorithms converge faster than discriminative algorithms. Therefore, we prefer generative models when we have a small training dataset.Although generative models converge faster, they converge to higher asymptotic errors. On the contrary, discriminative models converge to smaller asymptotic errors. Therefore, as the number of training samples increases, the error rate of discriminative models decreases.

## LDA 

LDA is a supervised learning dimensionality reduction technique, meaning that each sample in its dataset has a class label output. This is different from PCA, an unsupervised dimensionality reduction technique that does not consider the class label output of samples. The idea of LDA can be summarized in one sentence: "Minimize within-class variance and maximize between-class variance after projection." What does this mean? We want to project the data onto a lower dimension such that the projection points of each class are as close as possible to each other, while the distances between the centers of different classes are maximized as much as possible.

## Unsupervised learning

Unsupervised learning is a type of machine learning that deals with unlabeled or unannotated data. The goal of this learning approach is to explore the intrinsic structure and patterns in data, rather than predicting or classifying known outputs.

### Key Concepts and Techniques

1. Unlabeled Data: At the heart of unsupervised learning is the use of data that does not come with pre-defined labels or categories. The algorithms are designed to identify patterns and structures without external guidance or annotations.

2. Clustering: This technique involves grouping data points based on similarity measures. Clustering algorithms, like K-means, are used extensively for segmenting data into distinct groups, each representing a specific characteristic or feature within the data.

3. Dimensionality Reduction: Techniques such as Principal Component Analysis (PCA) are employed to reduce the number of variables under consideration. This process simplifies the dataset while retaining its essential characteristics, facilitating easier visualization and analysis.

4. Association Rules: Used predominantly in large datasets to find interesting relationships between variables. Market basket analysis is a classic example, revealing product purchasing patterns in retail.

### Applications of Unsupervised Learning
Unsupervised learning has a broad range of applications:

- Market Segmentation: Identifying distinct customer clusters for targeted marketing strategies.
- Recommendation Systems: Suggesting products or services to users based on their historical preferences.
- Anomaly Detection: Recognizing unusual patterns that could indicate fraudulent activity or system faults.
- Social Network Analysis: Uncovering structures within social platforms, such as community clusters.

## Semi-supervised learning

Semi-Supervised Learning is a hybrid approach in machine learning that utilizes both labeled and unlabeled data for training. This approach is particularly useful when acquiring a fully labeled dataset is costly or impractical, but unlabeled data is abundant. Semi-supervised learning bridges the gap between supervised and unsupervised learning, leveraging the strengths of both to improve learning accuracy and efficiency.

### Key Principles and Methods
1. Combining Labeled and Unlabeled Data: The core of semi-supervised learning is the combination of a small amount of labeled data with a large amount of unlabeled data during the training process.

2. Self-training: A common technique where a model initially trained on a small labeled dataset is used to label the unlabeled data. The model is then retrained on this newly labeled dataset.

3. Co-training: This involves training two separate models on different views of the data and then using each model to label the unlabeled data for the other model.

4. Graph-based Methods: These methods use graph structures to represent data, exploiting the relationships between labeled and unlabeled points to propagate labels through the graph.

### Applications and Use Cases

Semi-supervised learning is widely applicable in scenarios where labeled data is scarce or expensive to obtain:

- Natural Language Processing (NLP): For tasks like sentiment analysis and language translation where labeled data can be limited.
- Image and Video Recognition: Where labeling large datasets of images or videos is labor-intensive.
- Medical Diagnosis: In fields where labeled data requires expert knowledge and time-consuming annotation.

### Semi-Supervised SVM

In semi-supervised learning, semi-supervised support vector machines are more widely used methods.

Semi-Supervised Support Vector Machine (S3VM) is an extension of the traditional Support Vector Machine that combines a small amount of labeled data with a large volume of unlabeled data for training. The core idea of S3VM is to find the optimal separating hyperplane while utilizing the distribution information of the unlabeled data to guide the process. This approach aims to maximize the margin between labeled data points while ensuring a reasonable classification of the unlabeled data along this boundary. S3VM is particularly effective in scenarios where labeled data is scarce, but it involves a more complex optimization problem and may require more computational resources. Despite these challenges, S3VM has shown significant potential in enhancing classification performance, especially in situations where there is an abundance of unlabeled data available.

## How to conceive a "new" Machine Learning algorithm

- Using Perpendicular Distance Instead of Vertical Distance in Linear Regression
  - Modified linear regression model. This approach may require redefining the loss function to minimize the perpendicular distance from data points to the regression line, instead of the traditional vertical error. This variant of traditional linear regression might be more suitable for certain types of data distributions.

- Logistic Regression with Kernel Trick
  - Kernel logistic regression. By applying the kernel trick, logistic regression can be extended to handle non-linear relationships. The kernel trick involves mapping data into a higher-dimensional space where linearly inseparable data can become separable.

- Neural Network with Kernel Trick
  - Kernelized neural network. This is a theoretical concept where certain layers or operations in a neural network might be enhanced using kernel functions to better capture non-linear patterns in data. This approach could increase the complexity and computational demands of the model.

- Neural Network with Non-Hierarchical Structure
  - Graph Neural Networks (GNN) or other non-traditional structured neural networks. These networks do not follow the typical layered structure but are connected in different ways, such as based on the graph structure of the data.

- Horizontal or Vertical Lines - Decision Trees
  - Decision trees. This is a rule-based learning method that makes predictions by building a series of decisions based on features. Decision trees create splits in feature space, which can be seen as horizontal or vertical lines.

- Counting Numbers - K-Nearest Neighbors (KNN)
  - K-Nearest Neighbors algorithm. This is an instance-based learning method that predicts the classification of a sample point by looking at its K nearest neighbors. It is based on the principle of similarity, where similar samples tend to have similar outputs.

- K-Nearest Neighbors with Kernel Trick
  - Related Method: Kernelized K-Nearest Neighbors. This method extends KNN by measuring similarity in a high-dimensional space, allowing the algorithm to recognize non-linear relationships in the original feature space.

## Your turn! 🚀

TBD

    https://www.baeldung.com/cs/svm-vs-neural-network

---

> 编辑说明：本稿完成来源、许可证、文本结构、危险嵌入、知识点映射和部署可读性检查；学科正确性与教学难度仍应由课程负责人抽检后持续迭代。
