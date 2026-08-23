export type NavKey = "today" | "diagnostic" | "plan" | "records" | "qa" | "profile" | "goals" | "settings" | "resources" | "help";
export type TaskStatus = "completed" | "in_progress" | "todo" | "review_due" | "skipped" | "rescheduled";
/** 书籍 ID 由后端目录接口（GET /books）提供，前端不再限定取值。 */
export type BookId = string;

export type Book = { id: BookId; title: string; shortTitle: string; subtitle: string };
export type KnowledgeNode = { label: string; tone: "good" | "learning" | "weak" | "neutral"; left: string; top: string; description: string };
export type LearningTask = { id: string; title: string; type: string; minutes: number; status: TaskStatus; reason: string; description: string; learningGoal?: string; expectedCompletionDate?: string; knowledgePointIds?: string[]; abilityId?: string; chapterIds?: string[]; questionIds?: string[] };
export type DiagnosticQuestion = { id: string; title: string; tag: string; options: Array<{ id: string; text: string }> };
export type RecordItem = { id: string; title: string; description: string; time: string; tone: string; category: "profile" | "task" | "diagnostic" | "qa"; icon: "check" | "target" | "chat" | "calendar" };
export type Source = {
  id: string;
  type: string;
  title: string;
  location: string;
  excerpt: string;
  chapterId?: string;
  sectionId?: string;
  contentUnitId?: string;
  knowledgePointIds?: string[];
  bookId?: string;
};

/**
 * 书籍 ID -> 后端 learning_domain。
 * 后端 /books 接口就绪后应由接口直接返回该字段，这里只是过渡映射。
 */
export const bookLearningDomains: Record<string, string> = {
  ml: "machine_learning",
  dl: "deep_learning",
};

export const books: Book[] = [
  { id: "ml", title: "《机器学习》", shortTitle: "机器学习", subtitle: "监督学习与模型评估" },
  { id: "dl", title: "《深度学习》", shortTitle: "深度学习", subtitle: "神经网络、训练与泛化" },
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

const deepLearning: BookContent = {
  goal: "掌握深度学习基础",
  recommendation: { title: "理解反向传播与优化", minutes: 20, difficulty: "中等", reason: "最近诊断显示你需要加强神经网络训练、反向传播和泛化之间关系的理解。" },
  lastLearned: "神经网络基础",
  nodes: [
    { label: "神经网络", tone: "good", left: "8%", top: "17%", description: "理解层、参数、激活函数与输出之间的关系。" },
    { label: "反向传播", tone: "good", left: "67%", top: "17%", description: "利用链式法则计算参数梯度。" },
    { label: "优化与训练", tone: "weak", left: "5%", top: "49%", description: "当前重点：理解损失函数、梯度下降和学习率。" },
    { label: "多层感知机", tone: "learning", left: "72%", top: "49%", description: "组合线性变换与非线性激活完成表示学习。" },
    { label: "卷积网络", tone: "learning", left: "8%", top: "78%", description: "使用局部连接和参数共享处理空间结构。" },
    { label: "正则化", tone: "neutral", left: "69%", top: "78%", description: "缓解过拟合并提升泛化能力。" },
    { label: "泛化评估", tone: "neutral", left: "41%", top: "88%", description: "比较训练集、验证集和测试集上的表现。" },
  ],
  todayTasks: [
    { id: "dl-t1", title: "神经网络基础", type: "视频学习", minutes: 15, status: "completed", reason: "基础内容", description: "理解层、参数、激活函数和输出。" },
    { id: "dl-t2", title: "反向传播", type: "阅读理解", minutes: 20, status: "completed", reason: "目标关联", description: "理解链式法则和梯度计算。" },
    { id: "dl-t3", title: "理解梯度下降更新", type: "能力诊断", minutes: 20, status: "in_progress", reason: "诊断薄弱点", description: "练习根据损失梯度更新网络参数。" },
    { id: "dl-t4", title: "正则化与泛化练习", type: "例题练习", minutes: 20, status: "todo", reason: "前置知识", description: "比较正则化对训练误差和泛化误差的影响。" },
    { id: "dl-t5", title: "深度学习训练闭环总结", type: "归纳总结", minutes: 15, status: "todo", reason: "目标提升", description: "整理从数据准备、模型训练到泛化评估的过程。" },
  ],
  planTasks: [
    { id: "dl-p1", title: "神经网络基础", type: "视频学习", minutes: 15, status: "completed", reason: "基础内容", description: "理解层、参数、激活函数和输出。" },
    { id: "dl-p2", title: "反向传播", type: "阅读理解", minutes: 20, status: "completed", reason: "目标关联", description: "理解链式法则和梯度计算。" },
    { id: "dl-p3", title: "理解梯度下降更新", type: "能力诊断", minutes: 20, status: "in_progress", reason: "诊断薄弱点", description: "练习根据损失梯度更新网络参数。" },
    { id: "dl-p4", title: "正则化与泛化练习", type: "例题练习", minutes: 20, status: "todo", reason: "前置知识", description: "比较不同正则化方法的使用场景。" },
    { id: "dl-p5", title: "深度学习训练闭环总结", type: "归纳总结", minutes: 15, status: "todo", reason: "目标提升", description: "整理从数据准备、模型训练到泛化评估的过程。" },
  ],
  questions: [
    { id: "dl-q1", title: "神经网络训练中，反向传播的主要作用是什么？", tag: "反向传播", options: [{ id: "A", text: "根据损失计算参数梯度" }, { id: "B", text: "增加训练数据数量" }, { id: "C", text: "删除隐藏层" }, { id: "D", text: "固定所有模型参数" }] },
    { id: "dl-q2", title: "训练误差持续下降而验证误差开始上升，最可能说明什么？", tag: "泛化与过拟合", options: [{ id: "A", text: "出现过拟合" }, { id: "B", text: "学习率一定为零" }, { id: "C", text: "训练集为空" }, { id: "D", text: "模型没有参数" }] },
    { id: "dl-q3", title: "卷积层中的参数共享主要带来什么好处？", tag: "卷积网络", options: [{ id: "A", text: "减少参数量并利用局部结构" }, { id: "B", text: "保证训练误差为零" }, { id: "C", text: "取消非线性激活" }, { id: "D", text: "不再需要验证集" }] },
  ],
  records: [
    { id: "dl-r1", title: "完成：反向传播", description: "阅读理解 · 深度学习基础", time: "今天 09:42", tone: "green", category: "task", icon: "check" },
    { id: "dl-r2", title: "诊断：模型泛化", description: "正确 7/12 · 置信度中等", time: "昨天 20:16", tone: "blue", category: "diagnostic", icon: "target" },
    { id: "dl-r3", title: "提交用户校准", description: "自评：需要加强 · 卷积网络", time: "昨天 20:20", tone: "violet", category: "diagnostic", icon: "calendar" },
    { id: "dl-r4", title: "资料问答：如何缓解过拟合？", description: "引用 2 个资料来源", time: "2 天前", tone: "amber", category: "qa", icon: "chat" },
  ],
  sources: [
    { id: "dl-s1", type: "教材", title: "第 3 章 · 反向传播", location: "P.86", excerpt: "反向传播利用链式法则计算损失函数对各层参数的梯度。" },
    { id: "dl-s2", type: "讲义", title: "正则化与泛化", location: "P.14", excerpt: "正则化通过约束模型复杂度降低过拟合风险并提升泛化能力。" },
  ],
  qaQuestion: "如何缓解深度学习中的过拟合？",
  qaAnswer: "可以结合权重正则化、数据增强、早停、Dropout 和验证集监控，根据模型在验证集上的表现选择合适的复杂度。",
};

export const bookContents: Record<string, BookContent> = { ml: machineLearning, dl: deepLearning };
/** 目录中新增的书籍尚无本地演示内容时，回退到默认内容，避免页面崩溃。 */
export const getBookContent = (bookId: BookId): BookContent => bookContents[bookId] ?? machineLearning;
