import type { CommunityComment, CommunityPost } from "./communityState";

/** Fictional people and activity, for presentation only. No external avatars. */
export const communityPeople = [
  { id: "demo-mu", name: "小沐", color: "blue", role: "把抽象概念画成小图的人", course: "机器学习", goal: "理解模型背后的直觉", time: "工作日晚间 · 30分钟", bio: "正在学习模型评估和正则化。喜欢用生活里的例子解释概念，也想听听你的理解。", tags: ["图解笔记", "一起复盘"] },
  { id: "demo-lin", name: "林同学", color: "mint", role: "Python实践派", course: "机器学习", goal: "完成第一个分类项目", time: "周二 / 周四 · 20:00", bio: "刚开始系统学习人工智能，希望找到一起动手做练习的伙伴。遇到问题先尝试，再一起讨论。", tags: ["Python", "项目实操"] },
  { id: "demo-yu", name: "阿予", color: "violet", role: "喜欢追问为什么", course: "深度学习", goal: "读懂神经网络训练过程", time: "周末上午 · 1小时", bio: "在学反向传播与梯度下降。希望通过讲给别人听，把每一个知识点真正弄明白。", tags: ["概念讨论", "互相讲解"] },
  { id: "demo-ke", name: "可可", color: "peach", role: "每天进步一点点", course: "机器学习", goal: "搭建自己的知识地图", time: "每天午休 · 20分钟", bio: "用短时间持续学习，正在整理机器学习基础笔记。欢迎交换阅读心得与课程资源。", tags: ["阅读分享", "学习打卡"] },
] as const;
export type CommunityPerson = typeof communityPeople[number];

export const communityPosts: CommunityPost[] = [
  { id: "seed-1", authorId: "demo-mu", authorName: "小沐", category: "学习分享", course: "机器学习", title: "终于分清了过拟合和欠拟合，分享我的三句话笔记", body: "以前总觉得训练分数高就是学得好。今天把训练集和验证集放在一起看，才发现模型也会“死记硬背”。\n我的理解是：先看两边的误差，再想模型是不是太简单或太复杂。你们是怎么记住这个区别的？", createdAt: "示例 · 今天 09:20", likes: 24 },
  { id: "seed-2", authorId: "demo-lin", authorName: "林同学", category: "寻找搭子", course: "机器学习", title: "找一个一起做分类小项目的搭子，每周两次就好", body: "已经学完线性回归，想从一个小数据集开始练习：数据清洗 → 模型训练 → 结果分析。周二、周四晚上一起学，不赶进度，互相解释卡住的地方。", createdAt: "示例 · 今天 08:45", likes: 12 },
  { id: "seed-3", authorId: "demo-yu", authorName: "阿予", category: "问题讨论", course: "深度学习", title: "学习率调小之后更稳定了，但一定更好吗？", body: "画了几组损失曲线，发现学习率太小会收敛得很慢。除了观察曲线，大家还会通过哪些现象判断学习率是否合适？希望先讨论思路。", createdAt: "示例 · 昨天 21:10", likes: 18 },
  { id: "seed-4", authorId: "demo-ke", authorName: "可可", category: "学习分享", course: "机器学习", title: "今天的20分钟：用一个例子理解精确率和召回率", body: "把两个指标放进“找出所有目标样本”的场景里，再回头看混淆矩阵，一下就清楚了。准备明天用自己的话再讲一次，看看是不是真的理解了。", createdAt: "示例 · 昨天 12:30", likes: 9 },
  { id: "seed-5", authorId: "demo-yu", authorName: "阿予", category: "寻找搭子", course: "深度学习", title: "周末一起拆解反向传播：轮流讲解，不求一步到位", body: "想找一位也在学神经网络的朋友，从最简单的计算图开始。每次各讲一个小问题，遇到不懂的就画下来，下次一起解决。", createdAt: "示例 · 周一 10:00", likes: 7 },
];

export const communityComments: CommunityComment[] = [
  { id: "seed-c1", postId: "seed-1", authorName: "可可", body: "我的记法是：练习题和新题都做不好，先检查是不是还没学到位。" },
  { id: "seed-c2", postId: "seed-1", authorName: "林同学", body: "把训练误差和验证误差画成两条线，也很直观！" },
  { id: "seed-c3", postId: "seed-3", authorName: "小沐", body: "可以比较相同训练步数下的损失变化，再观察是否出现振荡。" },
];

export const communityGroups = [
  { id: "group-ml", name: "机器学习入门小组", detail: "概念互讲 · 每周复盘", icon: "book-open", color: "blue" },
  { id: "group-python", name: "Python实操同行", detail: "小项目起步 · 一起动手", icon: "file", color: "mint" },
  { id: "group-dl", name: "深度学习研习室", detail: "从计算图到神经网络", icon: "spark", color: "violet" },
] as const;
