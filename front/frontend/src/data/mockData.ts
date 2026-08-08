export type NavKey = "today" | "diagnostic" | "plan" | "records" | "qa" | "profile";
export type TaskStatus = "completed" | "in_progress" | "todo" | "review_due" | "skipped" | "rescheduled";
export type BookId = "ml" | "rl";

export type Book = { id: BookId; title: string; shortTitle: string; subtitle: string };
export type KnowledgeNode = { label: string; tone: "good" | "learning" | "weak" | "neutral"; left: string; top: string; description: string };
export type LearningTask = { id: string; title: string; type: string; minutes: number; status: TaskStatus; reason: string; description: string };
export type DiagnosticQuestion = { id: string; title: string; tag: string; options: Array<{ id: string; text: string }> };
export type RecordItem = { id: string; title: string; description: string; time: string; tone: string; category: "task" | "diagnostic" | "qa"; icon: "check" | "target" | "chat" | "calendar" };
export type Source = { id: string; type: string; title: string; location: string; excerpt: string };

export const books: Book[] = [
  { id: "ml", title: "《机器学习》", shortTitle: "机器学习", subtitle: "监督学习与模型评估" },
  { id: "rl", title: "《强化学习》", shortTitle: "强化学习", subtitle: "状态、动作与价值函数" },
];

type BookContent = {
  goal: string;
  recommendation: { title: string; minutes: number; difficulty: string; reason: string };
  lastLearned: string;
  nodes: KnowledgeNode[];
  todayTasks: LearningTask[];
  planTasks: LearningTask[];
  questions: DiagnosticQuestion[];
  records: RecordItem[];
  sources: Source[];
  qaQuestion: string;
  qaAnswer: string;
};

const machineLearning: BookContent = {
  goal: "掌握监督学习基础",
  recommendation: { title: "理解偏差与方差", minutes: 20, difficulty: "中等", reason: "最近诊断显示你在模型泛化和误差分析上的正确率为 61%，先补齐偏差与方差，有助于后续选择合适的模型复杂度。" },
  lastLearned: "线性回归与损失函数",
  nodes: [
    { label: "线性模型", tone: "good", left: "8%", top: "17%", description: "理解特征、参数与预测结果之间的关系。" },
    { label: "模型评估", tone: "learning", left: "67%", top: "17%", description: "掌握训练集、验证集和测试集的分工。" },
    { label: "偏差与方差", tone: "weak", left: "5%", top: "49%", description: "当前重点：分析欠拟合和过拟合。" },
    { label: "正则化", tone: "learning", left: "72%", top: "49%", description: "通过约束模型复杂度改善泛化。" },
    { label: "特征工程", tone: "good", left: "8%", top: "78%", description: "把原始数据转成更适合模型学习的表示。" },
    { label: "交叉验证", tone: "neutral", left: "69%", top: "78%", description: "稳定估计模型在未知数据上的表现。" },
    { label: "梯度下降", tone: "neutral", left: "41%", top: "88%", description: "通过迭代优化损失函数。" },
  ],
  todayTasks: [
    { id: "ml-t1", title: "线性回归与损失函数", type: "视频学习", minutes: 15, status: "completed", reason: "基础内容", description: "回顾参数、预测值与损失函数的关系。" },
    { id: "ml-t2", title: "模型评估指标", type: "阅读理解", minutes: 20, status: "completed", reason: "目标关联", description: "比较准确率、精确率和召回率的使用场景。" },
    { id: "ml-t3", title: "理解偏差与方差", type: "能力诊断", minutes: 20, status: "in_progress", reason: "诊断薄弱点", description: "通过例题判断模型的欠拟合和过拟合。" },
    { id: "ml-t4", title: "正则化例题练习", type: "例题练习", minutes: 20, status: "todo", reason: "前置知识", description: "练习 L1、L2 正则化对模型的影响。" },
    { id: "ml-t5", title: "模型选择归纳总结", type: "归纳总结", minutes: 15, status: "todo", reason: "目标提升", description: "整理模型复杂度和泛化能力之间的权衡。" },
  ],
  planTasks: [
    { id: "ml-p1", title: "线性回归与损失函数", type: "视频学习", minutes: 15, status: "completed", reason: "基础内容", description: "回顾参数、预测值与损失函数的关系。" },
    { id: "ml-p2", title: "模型评估指标", type: "阅读理解", minutes: 20, status: "completed", reason: "目标关联", description: "比较不同评估指标的使用场景。" },
    { id: "ml-p3", title: "理解偏差与方差", type: "能力诊断", minutes: 20, status: "in_progress", reason: "诊断薄弱点", description: "通过例题判断模型的欠拟合和过拟合。" },
    { id: "ml-p4", title: "正则化例题练习", type: "例题练习", minutes: 20, status: "todo", reason: "前置知识", description: "练习正则化对模型泛化的影响。" },
    { id: "ml-p5", title: "模型选择归纳总结", type: "归纳总结", minutes: 15, status: "todo", reason: "目标提升", description: "整理模型复杂度和泛化能力之间的权衡。" },
  ],
  questions: [
    { id: "ml-q1", title: "一个模型在训练集上误差很低、验证集上误差较高，最可能出现了什么问题？", tag: "偏差与方差", options: [{ id: "A", text: "欠拟合，模型复杂度不足" }, { id: "B", text: "过拟合，泛化能力不足" }, { id: "C", text: "训练数据完全没有噪声" }, { id: "D", text: "学习率一定过低" }] },
    { id: "ml-q2", title: "将数据划分为训练集、验证集和测试集的主要目的是什么？", tag: "模型评估", options: [{ id: "A", text: "让模型记住更多训练样本" }, { id: "B", text: "分别完成训练、调参与最终评估" }, { id: "C", text: "减少特征数量" }, { id: "D", text: "保证每个模型都达到相同准确率" }] },
    { id: "ml-q3", title: "增加模型复杂度后，训练误差下降而验证误差上升，下一步更适合尝试什么？", tag: "正则化", options: [{ id: "A", text: "增加正则化或减少模型复杂度" }, { id: "B", text: "删除验证集" }, { id: "C", text: "只增加训练轮数" }, { id: "D", text: "把测试集加入训练集" }] },
  ],
  records: [
    { id: "ml-r1", title: "完成：模型评估指标", description: "阅读理解 · 监督学习基础", time: "今天 09:42", tone: "green", category: "task", icon: "check" },
    { id: "ml-r2", title: "诊断：偏差与方差", description: "正确 7/10 · 置信度中等", time: "昨天 20:16", tone: "blue", category: "diagnostic", icon: "target" },
    { id: "ml-r3", title: "提交用户校准", description: "自评：基本符合 · 模型评估", time: "昨天 20:20", tone: "violet", category: "diagnostic", icon: "calendar" },
    { id: "ml-r4", title: "资料问答：如何判断过拟合？", description: "引用 2 个资料来源", time: "2 天前", tone: "amber", category: "qa", icon: "chat" },
  ],
  sources: [
    { id: "ml-s1", type: "教材", title: "第 4 章 · 模型评估", location: "P.118", excerpt: "验证集用于模型选择和超参数调整，测试集用于最终泛化表现评估。" },
    { id: "ml-s2", type: "讲义", title: "偏差与方差", location: "P.9", excerpt: "模型复杂度增加时，偏差通常下降，但方差可能上升。" },
  ],
  qaQuestion: "如何判断模型出现了过拟合？",
  qaAnswer: "可以比较训练集和验证集的表现：如果训练误差持续降低，而验证误差开始升高，通常说明模型正在过拟合。可以结合正则化、交叉验证或减少模型复杂度来改善。",
};

const reinforcementLearning: BookContent = {
  goal: "掌握强化学习基础",
  recommendation: { title: "理解 Q 学习更新", minutes: 20, difficulty: "中等", reason: "最近诊断显示你在状态价值和动作价值的区分上正确率为 58%，先理解 Q 学习更新，有助于建立从经验到策略的完整闭环。" },
  lastLearned: "马尔可夫决策过程",
  nodes: [
    { label: "状态与动作", tone: "good", left: "8%", top: "17%", description: "描述环境当前情况和可采取的行为。" },
    { label: "奖励函数", tone: "good", left: "67%", top: "17%", description: "定义智能体希望最大化的反馈。" },
    { label: "价值函数", tone: "weak", left: "5%", top: "49%", description: "当前重点：区分状态价值和动作价值。" },
    { label: "Q 学习", tone: "learning", left: "72%", top: "49%", description: "通过时序差分更新动作价值。" },
    { label: "探索与利用", tone: "learning", left: "8%", top: "78%", description: "在尝试新动作和使用已知策略间权衡。" },
    { label: "策略梯度", tone: "neutral", left: "69%", top: "78%", description: "直接优化策略参数。" },
    { label: "马尔可夫过程", tone: "neutral", left: "41%", top: "88%", description: "用状态转移描述环境动态。" },
  ],
  todayTasks: [
    { id: "rl-t1", title: "马尔可夫决策过程", type: "视频学习", minutes: 15, status: "completed", reason: "基础内容", description: "理解状态、动作、奖励和转移概率。" },
    { id: "rl-t2", title: "奖励与回报", type: "阅读理解", minutes: 20, status: "completed", reason: "目标关联", description: "区分即时奖励和折扣回报。" },
    { id: "rl-t3", title: "理解 Q 学习更新", type: "能力诊断", minutes: 20, status: "in_progress", reason: "诊断薄弱点", description: "练习根据下一状态价值更新当前动作价值。" },
    { id: "rl-t4", title: "探索与利用练习", type: "例题练习", minutes: 20, status: "todo", reason: "前置知识", description: "比较贪心策略和 ε-贪心策略。" },
    { id: "rl-t5", title: "强化学习闭环总结", type: "归纳总结", minutes: 15, status: "todo", reason: "目标提升", description: "整理从环境交互到策略更新的过程。" },
  ],
  planTasks: [
    { id: "rl-p1", title: "马尔可夫决策过程", type: "视频学习", minutes: 15, status: "completed", reason: "基础内容", description: "理解状态、动作、奖励和转移概率。" },
    { id: "rl-p2", title: "奖励与回报", type: "阅读理解", minutes: 20, status: "completed", reason: "目标关联", description: "区分即时奖励和折扣回报。" },
    { id: "rl-p3", title: "理解 Q 学习更新", type: "能力诊断", minutes: 20, status: "in_progress", reason: "诊断薄弱点", description: "练习根据下一状态价值更新当前动作价值。" },
    { id: "rl-p4", title: "探索与利用练习", type: "例题练习", minutes: 20, status: "todo", reason: "前置知识", description: "比较不同探索策略的使用场景。" },
    { id: "rl-p5", title: "强化学习闭环总结", type: "归纳总结", minutes: 15, status: "todo", reason: "目标提升", description: "整理从环境交互到策略更新的过程。" },
  ],
  questions: [
    { id: "rl-q1", title: "在强化学习中，智能体根据当前状态选择动作后，环境通常会返回什么？", tag: "状态与奖励", options: [{ id: "A", text: "下一状态和奖励" }, { id: "B", text: "训练集和测试集" }, { id: "C", text: "固定的正确答案" }, { id: "D", text: "模型参数梯度" }] },
    { id: "rl-q2", title: "Q 学习中的 Q 值主要表示什么？", tag: "价值函数", options: [{ id: "A", text: "某状态下所有动作的数量" }, { id: "B", text: "状态下采取动作并继续行动的预期回报" }, { id: "C", text: "环境的状态总数" }, { id: "D", text: "当前动作的执行时间" }] },
    { id: "rl-q3", title: "ε-贪心策略中的随机探索主要解决什么问题？", tag: "探索与利用", options: [{ id: "A", text: "避免永远只选择当前已知最优动作" }, { id: "B", text: "让所有奖励都变成正数" }, { id: "C", text: "减少状态数量" }, { id: "D", text: "取消价值函数" }] },
  ],
  records: [
    { id: "rl-r1", title: "完成：奖励与回报", description: "阅读理解 · 强化学习基础", time: "今天 09:42", tone: "green", category: "task", icon: "check" },
    { id: "rl-r2", title: "诊断：价值函数", description: "正确 7/12 · 置信度中等", time: "昨天 20:16", tone: "blue", category: "diagnostic", icon: "target" },
    { id: "rl-r3", title: "提交用户校准", description: "自评：低于判断 · Q 学习", time: "昨天 20:20", tone: "violet", category: "diagnostic", icon: "calendar" },
    { id: "rl-r4", title: "资料问答：如何平衡探索与利用？", description: "引用 2 个资料来源", time: "2 天前", tone: "amber", category: "qa", icon: "chat" },
  ],
  sources: [
    { id: "rl-s1", type: "教材", title: "第 3 章 · 价值函数", location: "P.86", excerpt: "动作价值函数衡量从当前状态采取某动作后，遵循策略能够获得的预期回报。" },
    { id: "rl-s2", type: "讲义", title: "探索与利用", location: "P.14", excerpt: "探索可以发现未知动作的潜在价值，利用则选择当前估计最优的动作。" },
  ],
  qaQuestion: "如何平衡强化学习中的探索与利用？",
  qaAnswer: "可以从 ε-贪心策略开始：大部分时间选择当前估计价值最高的动作，同时保留一小部分概率随机探索。随着学习推进，再逐步降低探索概率。",
};

export const bookContents: Record<BookId, BookContent> = { ml: machineLearning, rl: reinforcementLearning };
export const getBookContent = (bookId: BookId) => bookContents[bookId];
