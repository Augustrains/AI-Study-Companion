/**
 * 用内容负责人编写的独立题替换早期“换序变式”。
 * 先运行不带参数的校验；确认无误后使用 --apply 写入题库及其边表，并保存可恢复快照。
 */
import { access, mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const CONTENT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = resolve(CONTENT_ROOT, 'data');
const SNAPSHOT = resolve(DATA, '历史快照', '2026-07-31-独立掌握题替换前');
const apply = process.argv.includes('--apply');

function parseCsv(text) {
  const rows = []; let row = []; let cell = ''; let quoted = false;
  for (let i = 0; i < text.length; i += 1) { const char = text[i];
    if (quoted && char === '"' && text[i + 1] === '"') { cell += '"'; i += 1; continue; }
    if (char === '"') { quoted = !quoted; continue; }
    if (!quoted && char === ',') { row.push(cell); cell = ''; continue; }
    if (!quoted && (char === '\n' || char === '\r')) { if (char === '\r' && text[i + 1] === '\n') i += 1; row.push(cell); cell = ''; if (row.some(Boolean)) rows.push(row); row = []; continue; }
    cell += char;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [headers, ...values] = rows;
  return { headers, rows: values.map(valueRow => Object.fromEntries(headers.map((header, index) => [header, valueRow[index] ?? '']))) };
}
const esc = value => { const text = String(value ?? ''); return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text; };
const csv = (headers, rows) => `${headers.join(',')}\n${rows.map(row => headers.map(header => esc(row[header])).join(',')).join('\n')}\n`;
const load = async name => parseCsv(await readFile(resolve(DATA, name), 'utf8'));
const save = (name, file) => writeFile(resolve(DATA, name), csv(file.headers, file.rows), 'utf8');
const q = (type, difficulty, prompt, options, correct, explanation) => ({ type, difficulty, prompt, options, correct, explanation });

// 每题都使用新的情境与选项；类型必须能满足相应知识点的蓝图，不以“综合题”代替推导、代码或评价证据。
const variants = {
  'ml-q01': [
    q('应用题', 2, '一个推荐系统希望重视三个月后的用户留存，而不是只追求当天点击。下列哪种折扣因子设置更符合这一目标？', ['γ 接近 0，例如 0.05', 'γ 接近 1，例如 0.95', '把 γ 设为负数'], 1, '较大的折扣因子会让未来奖励在当前决策中占更高权重。'),
    q('推导题', 3, '某策略的两步奖励依次为 1 和 4，终止后无奖励。若 γ=0.5，从第一步开始的折扣回报是多少？', ['2', '3', '5'], 1, '回报为 1+0.5×4=3。'),
    q('复测题', 2, '无提示复测：当 γ 从 0.9 调低到 0.1 时，智能体的决策会更倾向于哪一类奖励？', ['很久以后的奖励', '即时奖励', '两者权重完全不变'], 1, 'γ 变小会明显降低远期奖励的贡献。')
  ],
  'ml-q02': [
    q('概念题', 1, '在强化学习中，“回报”与“单步奖励”的关系最准确的是？', ['回报只等于当前一步奖励', '回报可以累计当前及未来奖励', '回报只由动作数量决定'], 1, '回报描述从当前时刻开始的累计奖励。'),
    q('推导题', 3, '从时刻 t 开始，奖励依次为 3、2、1，γ=0.5。G_t 的值是多少？', ['4.25', '5', '6'], 0, 'G_t=3+0.5×2+0.5²×1=4.25。'),
    q('复测题', 2, '无提示复测：若终止状态之后的价值定义为 0，终止前一步的回报最直接由什么决定？', ['该步即时奖励', '下一轮训练的学习率', '网络隐藏层数'], 0, '终止后没有未来回报，因此只剩当前奖励。')
  ],
  'ml-q03': [
    q('应用题', 2, '机器人在仓库中移动：位置会改变，机器人可选择上下左右，撞墙会得到 -1，到达终点得 +10。下列哪项最像该问题的“状态”？', ['机器人当前位置', '训练轮数', '神经网络层数'], 0, '位置刻画机器人此刻可观察到的决策环境。'),
    q('情境题', 2, '设计一个 MDP 来描述电梯调度时，哪个信息应作为“动作”而不是“奖励”？', ['选择上行、下行或停留', '乘客等待时间的负值', '下一层的乘客数量'], 0, '动作是决策者主动选择的行为。'),
    q('复测题', 2, '无提示复测：MDP 中的转移概率 P(s′|s,a) 表示什么？', ['采取动作后到达下一状态的可能性', '模型参数总数', '每轮必定获得的固定奖励'], 0, '它描述状态与动作条件下的环境不确定性。')
  ],
  'ml-q04': [
    q('概念题', 1, '动态规划能够求解许多序贯决策问题的关键前提是？', ['问题可分解为重叠子问题和递推关系', '必须使用深度神经网络', '所有奖励都相同'], 0, '动态规划利用子问题结果构造整体解。'),
    q('推导题', 3, '某状态执行动作后立即奖励为 2，必定转移到价值为 6 的下一状态，γ=0.5。按贝尔曼期望形式，该动作价值为多少？', ['4', '5', '8'], 1, 'Q=2+0.5×6=5。'),
    q('复测题', 2, '无提示复测：贝尔曼方程中的“未来部分”通常来自哪里？', ['下一状态的价值估计', '数据文件的大小', '当前批次的样本数'], 0, '价值递推把未来回报压缩为下一状态价值。')
  ],
  'ml-q05': [
    q('概念题', 1, 'Q-Learning 与只记录状态价值 V(s) 的方法相比，Q(s,a) 额外区分了什么？', ['在状态中选择的具体动作', '训练集文件格式', '神经元激活函数'], 0, 'Q 函数评估状态—动作对的长期价值。'),
    q('应用题', 2, '一个智能体到达新状态后，希望按 Q-Learning 的贪心目标估计未来回报。它应查看什么？', ['新状态下所有动作 Q 值中的最大值', '历史上最小的奖励', '当前状态的编号'], 0, 'Q-Learning 的目标使用下一状态动作价值的最大值。'),
    q('复测题', 2, '无提示复测：在 Q-Learning 更新中，学习率 α 主要控制什么？', ['新观测对旧 Q 值的调整幅度', '状态数量', '折扣因子的正负'], 0, 'α 决定一次更新迈出的步长。')
  ],
  'ml-q06': [
    q('应用题', 2, '两个动作在同一状态的 Q 值分别为 3.2 和 2.7。若策略暂时采用纯贪心选择，应执行哪个动作？', ['Q 值为 3.2 的动作', 'Q 值为 2.7 的动作', '随机丢弃两个动作'], 0, '贪心策略选择当前估计价值最大的动作。'),
    q('代码题', 3, '阅读伪代码：`target = r + gamma * max(Q[next_state])`。若 next_state 是终止状态，常见实现应把 `max(Q[next_state])` 处理为？', ['0', '当前 Q 表最大元素', '动作总数'], 0, '终止状态之后没有未来回报。'),
    q('复测题', 2, '无提示复测：Q-Learning 属于哪类强化学习方法？', ['无模型价值学习', '监督分类', '无监督聚类'], 0, '它直接从交互经验更新动作价值，不需要已知环境模型。')
  ],
  'dl-q01': [
    q('应用题', 2, '一个神经元有两个输入 2、-1，权重 0.5、1，偏置 1。激活函数之前的线性输出是多少？', ['1', '2', '3'], 0, '0.5×2+1×(-1)+1=1。'),
    q('推导题', 3, '若神经元线性部分 z=wᵀx+b，所有输入 x 同时变为 0，而 b=2，则 z 为多少？', ['0', '2', '无法确定'], 1, '输入项为 0，只留下偏置 b。'),
    q('复测题', 2, '无提示复测：偏置项的主要作用是什么？', ['平移线性变换的输出', '删除输入特征', '保证输出一定为 0'], 0, '偏置允许模型在输入为零时仍产生非零输出。')
  ],
  'dl-q02': [
    q('应用题', 2, '若一个多层网络的所有层都使用恒等激活函数，它与单层线性模型相比最接近哪种情况？', ['整体仍是线性变换', '一定能表示任意非线性函数', '不再需要参数'], 0, '线性变换的复合仍是线性变换。'),
    q('推导题', 3, 'ReLU(x)=max(0,x)。当输入分别为 -2、3 时，输出分别是？', ['-2、3', '0、3', '0、0'], 1, 'ReLU 将负值截为 0，保留正值。'),
    q('复测题', 2, '无提示复测：为什么隐藏层常需要非线性激活函数？', ['否则多层网络会退化为线性映射', '为了增加训练样本', '为了替代优化器'], 0, '非线性让网络能够表达更复杂的函数。')
  ],
  'dl-q03': [
    q('概念题', 1, '前向传播的核心任务是？', ['用当前参数从输入计算预测', '直接修改梯度', '删除训练样本'], 0, '前向传播产生后续计算损失所需的预测。'),
    q('代码题', 3, '在训练代码中，`y_hat = net(X)` 之后通常紧接着哪一行最合理？', ['`loss = loss_fn(y_hat, y)`', '`optimizer.step()`', '`del y_hat`'], 0, '先由预测和真实标签计算损失，才可反向传播。'),
    q('复测题', 2, '无提示复测：若模型参数不变、输入相同，确定性的前向传播应产生什么？', ['相同预测', '随机梯度', '更多训练标签'], 0, '确定性网络在相同输入和参数下输出一致。'),
    q('推导题', 3, '对单样本线性模型 ŷ=wx，平方损失 L=(ŷ-y)²。若 x=2、w=1、y=3，L 为多少？', ['1', '4', '9'], 0, 'ŷ=2，故 L=(2-3)²=1。')
  ],
  'dl-q04': [
    q('概念题', 1, '反向传播利用哪条基本规则把损失对后一层的影响传回前一层？', ['链式法则', '鸽巢原理', '贝叶斯先验'], 0, '链式法则连接复合函数各层的导数。'),
    q('推导题', 3, '若 L=(z-4)²，且 z=3w，w=1。dL/dw 等于多少？', ['-6', '-3', '6'], 0, 'dL/dz=2(z-4)=-2，dz/dw=3，因此 dL/dw=-6。'),
    q('复测题', 2, '无提示复测：梯度的符号和大小在训练中主要用于什么？', ['决定参数更新方向和步长', '确定类别数量', '替代输入数据'], 0, '优化器依据梯度更新参数。')
  ],
  'dl-q05': [
    q('概念题', 1, '训练循环中 `optimizer.zero_grad()` 的常见作用是？', ['清除上一批次累积的梯度', '删除模型参数', '计算测试集准确率'], 0, '多数框架会累积梯度，训练新批次前需清零。'),
    q('应用题', 2, '训练损失连续上升且学习率较大时，最合理的首个排查方向是？', ['降低学习率并观察稳定性', '删除全部训练数据', '把标签都改成 0'], 0, '过大的步长可能导致优化震荡或发散。'),
    q('复测题', 2, '无提示复测：以下哪个顺序正确？', ['前向→损失→清梯度→反向→更新', '更新→前向→删除损失', '反向→不计算损失→更新'], 0, '训练需先得到损失，再计算梯度并更新。')
  ],
  'dl-q06': [
    q('概念题', 1, '在监督学习训练中，损失函数的输入通常是一对什么？', ['模型预测与真实标签', '学习率与批次大小', '层数与文件名'], 0, '损失衡量预测与目标之间的差异。'),
    q('代码题', 3, '下列哪段伪代码会真正更新参数？', ['`loss.backward(); optimizer.step()`', '`loss = loss_fn(y_hat,y); print(loss)`', '`optimizer.zero_grad(); break`'], 0, '反向传播生成梯度，step 使用梯度更新参数。'),
    q('复测题', 2, '无提示复测：若跳过反向传播直接调用 optimizer.step()，在常规训练中最可能发生什么？', ['没有当前损失对应的新梯度可用于更新', '自动得到最佳模型', '标签数会翻倍'], 0, '优化器需要由反向传播计算出的梯度。')
  ],
  'ml-q07': [
    q('概念题', 1, '监督学习与无监督学习的主要区别之一是？', ['监督学习使用带目标标签的数据', '无监督学习一定不使用数据', '监督学习不能预测数值'], 0, '监督学习依赖输入与目标的对应关系。'),
    q('分类题', 2, '把“根据用户历史行为把用户自动分组”归为哪类任务最合适？', ['聚类', '回归', '序列标注'], 0, '没有预先标签时按相似性分组属于聚类。'),
    q('情境题', 2, '医院希望根据既往体检指标预测患者下月的具体血压数值，应优先建立什么任务？', ['回归', '二分类', '聚类'], 0, '目标是连续数值。'),
    q('复测题', 2, '无提示复测：判断图片是“猫”还是“狗”通常属于？', ['分类', '回归', '降维'], 0, '输出是离散类别。')
  ],
  'ml-q08': [
    q('解释题', 2, '为什么机器学习训练通常需要区分训练集与验证集？', ['用验证集检查模型对未参与拟合数据的表现', '因为验证集专门用来记住答案', '为了让参数永远不更新'], 0, '验证集支持模型选择和泛化检查。'),
    q('应用题', 2, '一个模型训练准确率很高、验证准确率明显较低。团队下一步最应关注什么？', ['过拟合与泛化问题', '把训练集重复复制', '固定所有参数不再训练'], 0, '训练与验证表现差距是过拟合信号。'),
    q('复测题', 2, '无提示复测：模型“学习”的直接含义最接近？', ['根据数据调整参数以改善任务表现', '把所有输入文件删除', '为每个样本手写固定答案'], 0, '学习通过数据和优化改变模型参数。')
  ],
  'ml-q09': [
    q('概念题', 1, '回归任务的预测目标通常是什么类型？', ['连续数值', '互斥类别名称', '无标签分组编号'], 0, '回归用于预测连续量。'),
    q('建模题', 3, '要预测二手车价格，特征包括里程、车龄和品牌。下面哪项最适合作为模型标签 y？', ['成交价格', '品牌名称列表', '训练轮数'], 0, 'y 是要预测的连续目标价格。'),
    q('复测题', 2, '无提示复测：预测某城市明日最高温度属于回归，因为输出是？', ['一个连续数值', '一个固定类别', '一个聚类中心'], 0, '温度可在连续数值范围内变化。')
  ],
  'ml-q10': [
    q('概念题', 1, '在线性回归 ŷ=wx+b 中，w 最直接表示什么？', ['输入变化对预测的线性影响系数', '训练样本数量', '类别总数'], 0, 'w 是输入特征的线性系数。'),
    q('代码题', 3, '下列哪句伪代码正确计算批量线性回归预测？', ['`y_hat = X @ w + b`', '`y_hat = X / y`', '`w = y_hat + labels`'], 0, '矩阵乘法加偏置是线性层的标准形式。'),
    q('复测题', 2, '无提示复测：若所有其他条件不变，b 增大 1，预测 ŷ 会怎样？', ['整体增加 1', '整体减少 1', '完全不变'], 0, '偏置以加法方式平移预测。')
  ],
  'ml-q11': [
    q('应用题', 2, '欺诈检测模型输出某笔交易为欺诈的概率 0.92，阈值设为 0.5。模型应输出什么类别？', ['欺诈', '非欺诈', '聚类中心'], 0, '概率超过阈值时预测为正类。'),
    q('代码题', 3, '阅读伪代码 `p = sigmoid(logit)`。若 logit=0，变量 p 的值应为？', ['0.5', '0', '1'], 0, 'sigmoid(0)=0.5，得到正类概率。'),
    q('复测题', 2, '无提示复测：逻辑回归的决策边界常由什么确定？', ['预测概率与设定阈值的比较', '样本文件大小', '随机种子名称'], 0, '阈值把概率转为类别决策。')
  ],
  'ml-q12': [
    q('概念题', 1, '训练时最小化损失函数的目的是什么？', ['让预测与真实目标更一致', '增加网络层数', '减少特征数量到零'], 0, '损失为优化提供误差目标。'),
    q('推导题', 3, '两条样本的真实值为 1、5，预测为 3、2。均方误差 MSE 为多少？', ['4', '6.5', '13'], 1, '((3-1)²+(2-5)²)/2=(4+9)/2=6.5。'),
    q('复测题', 2, '无提示复测：若预测完全等于真实目标，常见平方损失为？', ['0', '1', '无法定义'], 0, '误差为零时平方损失为零。')
  ],
  'ml-q13': [
    q('计算题', 2, '某参数当前为 5，梯度为 2，学习率为 0.1。按梯度下降更新后参数为？', ['4.8', '5.2', '7'], 0, 'w←5-0.1×2=4.8。'),
    q('代码题', 3, '下列哪一行体现了最基本的梯度下降更新？', ['`w = w - lr * grad_w`', '`w = w + lr * grad_w`', '`grad_w = 0; w = 0`'], 0, '最小化目标时沿负梯度方向更新。'),
    q('复测题', 2, '无提示复测：学习率过大最常见的风险是？', ['在最优点附近震荡或发散', '自动获得更多数据', '梯度一定变为零'], 0, '更新步长过大可能越过较优区域。')
  ],
  'ml-q14': [
    q('概念题', 1, '多分类任务的标签形式通常是？', ['有限个离散类别之一', '任意连续实数', '没有任何观测'], 0, '分类输出为离散类别。'),
    q('评价题', 3, '在疾病筛查中，漏掉真实患病者代价很高。下列哪个指标尤其应被关注？', ['召回率', '训练集文件大小', '模型参数个数'], 0, '召回率衡量真实正例被识别的比例。'),
    q('复测题', 2, '无提示复测：若模型要判断评论“正面/负面/中性”，输出空间是什么？', ['三个类别', '一个连续房价', '若干无标签簇'], 0, '情感标签是有限离散类别。')
  ],
  'ml-q15': [
    q('应用题', 2, '电商希望在没有人工标签的情况下按购买行为把用户分成若干群体，应优先使用？', ['聚类', '二分类', '线性回归'], 0, '目标是发现无标签数据中的群组。'),
    q('比较题', 2, '聚类和分类的主要差异是？', ['分类通常依赖已知标签，聚类不依赖', '聚类只能预测连续值', '分类不能使用特征'], 0, '监督分类与无监督聚类的标签条件不同。'),
    q('复测题', 2, '无提示复测：K-means 的目标直观上是让同一簇内样本怎样？', ['彼此更相似', '标签更多', '时间顺序更长'], 0, 'K-means 按距离把相近样本聚到一起。')
  ],
  'ml-q16': [
    q('应用题', 2, '多个分类器各自判断后，通过投票输出最终类别属于哪种思想？', ['集成学习', '单一线性回归', '无监督降维'], 0, '投票组合多个模型的预测。'),
    q('比较题', 2, 'Bagging 与 Boosting 的一个常见区别是？', ['Boosting 常序列地关注前一轮难分样本', 'Bagging 不使用任何模型', 'Boosting 只能做聚类'], 0, 'Boosting 会逐步调整对难样本的关注。'),
    q('复测题', 2, '无提示复测：集成模型可能提升稳健性的原因是？', ['不同模型的误差可部分互补', '它删除全部训练数据', '它保证没有参数'], 0, '组合多样模型可降低单一模型偏差或方差。')
  ],
  'ml-q17': [
    q('概念题', 1, '训练集、验证集、测试集的合理分工是？', ['训练拟合参数，验证选择方案，测试做最终一次评估', '测试集反复调参，验证集从不使用', '三者必须完全相同'], 0, '测试集应尽量保留给最后的泛化评估。'),
    q('应用题', 2, '两个模型训练完成后，团队要选择超参数。应优先比较它们在哪个集合上的结果？', ['验证集', '训练集', '最终测试集反复多次'], 0, '超参数选择应以验证集表现为依据。'),
    q('复测题', 2, '无提示复测：为什么不应反复根据测试集结果调参？', ['会把测试集信息泄露进模型选择过程', '测试集没有标签', '测试集只能保存图片'], 0, '反复使用测试集会高估泛化能力。')
  ],
  'dl-q07': [
    q('概念题', 1, '神经网络中用矩阵乘法处理一个批次输入的主要好处是？', ['可并行执行多个样本的线性变换', '自动产生标签', '取消所有权重'], 0, '矩阵运算适合批量线性计算。'),
    q('推导题', 3, '矩阵 A 为 2×3，矩阵 B 为 3×4，则 AB 的形状为？', ['2×4', '3×3', '4×2'], 0, '内维 3 匹配，结果保留外维 2 和 4。'),
    q('复测题', 2, '无提示复测：若向量 x 是 3 维，线性层输出为 5 维，权重矩阵常可表示为？', ['5×3', '3×5×3', '5×5'], 0, '每个输出维对应一组 3 维权重。')
  ],
  'dl-q08': [
    q('计算题', 2, '一枚公平硬币连续抛两次，恰好一次正面的概率是？', ['1/4', '1/2', '3/4'], 1, 'HT 和 TH 两种结果，共四种等可能结果。'),
    q('应用题', 2, '模型给两个类别的预测概率为 0.7 与 0.3。下列判断正确的是？', ['两类概率之和为 1，第一类更可能', '第一类一定真实', '概率不能用于分类'], 0, '概率表示不确定性，不保证单次预测必然正确。'),
    q('复测题', 2, '无提示复测：概率为 0 的事件表示？', ['在当前模型下不可能发生', '一定发生', '样本数为零'], 0, '概率 0 表示事件不发生。')
  ],
  'dl-q09': [
    q('计算题', 2, '线性模型 ŷ=2x，给定 x=3、真实值 y=7。平方误差为？', ['1', '4', '49'], 0, '预测为 6，误差为 -1，平方为 1。'),
    q('代码题', 3, 'PyTorch 风格伪代码中，哪一项是线性回归模型常见的可学习参数？', ['`w` 和 `b`', '类别名称字符串', '训练集路径'], 0, '线性模型通过权重和偏置拟合数据。'),
    q('复测题', 2, '无提示复测：若线性回归损失持续下降，通常说明？', ['当前训练数据上的预测误差在减小', '模型必然完全不过拟合', '测试准确率一定为 100%'], 0, '训练损失下降只直接说明训练目标在改善。')
  ],
  'dl-q10': [
    q('计算题', 2, 'Softmax 输入分数为 [0,0]，两个类别的输出概率分别是？', ['[0.5,0.5]', '[1,0]', '[0,1]'], 0, '相等分数经 Softmax 后得到相等概率。'),
    q('应用题', 2, '图像分类模型需要在“飞机、汽车、鸟”中选一个类别，输出层最适合使用？', ['Softmax 概率分布', '单个连续回归值', '聚类中心编号'], 0, '多个互斥类别通常使用 Softmax。'),
    q('复测题', 2, '无提示复测：Softmax 输出的各类别概率有何共同约束？', ['总和为 1', '每个都大于 1', '全部固定相等'], 0, 'Softmax 将分数归一化为概率分布。')
  ],
  'dl-q11': [
    q('推导题', 3, '一个 MLP 的输入层有 4 个特征，隐藏层有 3 个神经元（含偏置），输出层有 2 个神经元（含偏置）。可学习参数总数是多少？', ['23', '18', '12'], 0, '输入到隐藏层为 4×3+3=15，隐藏到输出为 3×2+2=8，共 23。'),
    q('代码题', 3, '下列哪段 PyTorch 风格结构能形成最基本的非线性 MLP？', ['`nn.Linear(4,3) → nn.ReLU() → nn.Linear(3,2)`', '`nn.Linear(4,2) → nn.Linear(2,2)` 且无激活', '`del input`'], 0, '在线性层之间加入 ReLU 引入非线性。'),
    q('复测题', 2, '无提示复测：MLP 比单层线性模型更有表达力的关键是？', ['隐藏层中的非线性变换', '训练文件名更长', '类别数量固定'], 0, '非线性与多层组合提升函数表示能力。')
  ],
  'dl-q12': [
    q('评价题', 3, '模型 A 训练准确率 99%、验证准确率 70%；模型 B 训练 90%、验证 88%。若要选泛化更好的模型，应选？', ['模型 B', '模型 A', '仅看谁训练准确率高'], 0, 'B 的验证表现更好且训练验证差距更小。'),
    q('应用题', 2, '发现过拟合后，下列哪项是合理应对？', ['增加正则化或数据增强', '只继续增加训练轮数', '删除验证集'], 0, '正则化和数据增强常用于改善泛化。'),
    q('复测题', 2, '无提示复测：泛化能力指模型在什么数据上的表现？', ['未参与训练的相似新数据', '仅训练样本', '随机文件名'], 0, '泛化关注未见样本上的效果。')
  ],
  'dl-q13': [
    q('解释题', 2, '为什么深层网络常关注 Xavier 或 He 初始化？', ['帮助前后向信号保持合适尺度', '让训练集自动扩容', '消除所有非线性'], 0, '合理初始化有助于缓解梯度消失或爆炸。'),
    q('实验题', 3, '比较两种初始化时，最能帮助判断是否数值不稳定的记录是？', ['各层激活和梯度的均值/方差随训练变化', '电脑桌面颜色', '数据文件创建时间'], 0, '激活和梯度统计能直接反映信号尺度。'),
    q('复测题', 2, '无提示复测：梯度长期接近 0 会使训练怎样？', ['参数更新非常缓慢', '学习率自动变大', '模型不再需要数据'], 0, '梯度过小导致更新幅度接近零。')
  ],
  'dl-q14': [
    q('计算题', 2, '输入特征图为 5×5，卷积核为 3×3，步幅 1、无填充。输出空间尺寸为？', ['3×3', '5×5', '7×7'], 0, '输出边长为 5-3+1=3。'),
    q('代码题', 3, '若希望输入通道为 3、输出通道为 16、卷积核 3×3，哪个配置最符合？', ['Conv2d(3,16,kernel_size=3)', 'Conv2d(16,3,kernel_size=1) 且无输入', 'Linear(3,16)'], 0, '卷积层需声明输入/输出通道和卷积核尺寸。'),
    q('复测题', 2, '无提示复测：卷积层的“局部连接”表示？', ['一个输出位置只看输入的局部邻域', '每个输出必须连接所有图像像素', '不使用任何权重'], 0, '卷积核在局部感受野内计算特征。')
  ],
  'dl-q15': [
    q('概念题', 1, '卷积中的填充（padding）最常用于什么？', ['控制边界信息与输出尺寸', '增加类别标签', '替代卷积核'], 0, '填充可减少边界缩小并保留边缘信息。'),
    q('应用题', 2, '输入为 32×32，卷积核 3×3、步幅 1。若希望输出仍是 32×32，应采用哪种填充？', ['padding=1', 'padding=0', 'padding=3'], 0, '输出边长为 32+2p-3+1，p=1 时为 32。'),
    q('复测题', 2, '无提示复测：步幅从 1 增至 2 通常会怎样？', ['减少输出位置数量', '增加输入通道数', '使卷积核消失'], 0, '卷积核移动更快，因此输出采样位置更少。')
  ],
  'dl-q16': [
    q('计算题', 2, '对 2×2 区域 [[1,4],[2,3]] 做最大池化，输出为？', ['4', '2.5', '1'], 0, '最大池化保留窗口最大值。'),
    q('比较题', 2, '平均池化与最大池化的主要区别是？', ['一个取平均值，一个取最大值', '二者都只做参数更新', '平均池化输出类别'], 0, '两者采用不同的局部汇聚规则。'),
    q('复测题', 2, '无提示复测：池化层通常不做什么？', ['学习卷积核权重', '降低空间分辨率', '汇聚局部特征'], 0, '标准池化没有可学习卷积核参数。')
  ],
  'dl-q17': [
    q('应用题', 2, '要用过去 7 天销量预测第 8 天销量，输入最合适的组织方式是？', ['按时间顺序的 7 天销量窗口', '随机打乱后只保留一天', '类别名称列表'], 0, '序列预测依赖历史顺序信息。'),
    q('建模题', 3, '为预测一句话的下一个词，模型输入和目标的合理配对是？', ['前面词序列 → 下一个词', '下一个词 → 随机图片', '词序列 → 文件大小'], 0, '语言建模根据前文预测后续 token。'),
    q('复测题', 2, '无提示复测：将时间序列样本任意打乱的主要风险是？', ['破坏时间依赖关系', '增加输入维度', '自动减少噪声'], 0, '顺序是序列数据的重要信息。')
  ],
  'dl-q18': [
    q('推导题', 3, '简单 RNN 中 h_t=tanh(W_hh h_{t-1}+W_xh x_t)。其中 h_{t-1} 的作用是？', ['携带先前时间步的信息', '记录训练文件路径', '替代当前输入 x_t'], 0, '隐藏状态把历史上下文传到当前时刻。'),
    q('代码题', 3, '循环体为 `h = tanh(W_hh @ h + W_xh @ x_t)`。连续处理序列时，变量 h 在下一时间步应如何使用？', ['作为下一步的上一隐藏状态继续输入', '每步删除并改为 0', '替代当前输入 x_t'], 0, 'RNN 将当前 h 传递到下一时间步以保存历史信息。'),
    q('复测题', 2, '无提示复测：普通 RNN 在很长序列上可能遇到的训练困难是？', ['梯度消失或爆炸', '类别标签自动删除', '输入维度必定为 0'], 0, '反复链式相乘会导致梯度尺度不稳定。')
  ]
};

const baseFixes = {
  'ml-q05': q('代码题', 3, '阅读 Q 表更新代码：`q=1.5; r=2; gamma=0.5; max_next=4; alpha=0.1; q = q + alpha*(r + gamma*max_next - q)`。更新后的 q 是多少？', ['1.25', '1.75', '4.00'], 1, '目标为 2+0.5×4=4，q 更新为 1.5+0.1×(4-1.5)=1.75。'),
  'ml-q12': q('计算题', 2, '两条样本真实值为 2、4，预测为 3、1。均方误差 MSE 是多少？', ['2.5', '5', '10'], 1, 'MSE=((3-2)²+(1-4)²)/2=5。'),
  'ml-q17': q('评价题', 2, '训练完成后要在多个超参数方案中选择一个，最合适的数据依据是？', ['验证集表现', '训练集表现', '最终测试集反复调参'], 0, '验证集用于模型选择；测试集保留给最后评估。'),
  'dl-q05': q('代码题', 3, '训练代码为：`y_hat=net(X); loss=loss_fn(y_hat,y); optimizer.zero_grad(); loss.backward(); optimizer.step()`。其中真正根据梯度修改参数的是哪一行？', ['`loss_fn(y_hat,y)`', '`loss.backward()`', '`optimizer.step()`'], 2, 'backward 计算梯度，optimizer.step 使用梯度更新参数。'),
  'dl-q07': q('计算题', 2, '矩阵 A=[[1,2],[3,4]]，向量 x=[1,0]。A x 的结果是？', ['[1,3]', '[2,4]', '[3,7]'], 0, '矩阵乘向量得到 [1×1+2×0,3×1+4×0]=[1,3]。'),
  'dl-q09': q('概念题', 1, '深度学习中的线性回归训练希望通过调整参数使什么尽量变小？', ['预测与真实值之间的损失', '训练数据的行数', '输入特征的名称数'], 0, '线性网络根据损失信号更新参数。')
};

const [bank, knowledge, abilities, sources, blueprints] = await Promise.all(['question_bank.csv', 'question_knowledge_edges.csv', 'question_ability_edges.csv', 'question_source_edges.csv', 'question_blueprint_catalog.csv'].map(load));
const isVariant = questionId => /-v\d+$/.test(questionId);
const baseRows = bank.rows.filter(row => !isVariant(row.question_id));
if (Object.keys(variants).length !== baseRows.length) throw new Error(`题目定义不完整：基础题 ${baseRows.length} 道，独立题配置 ${Object.keys(variants).length} 组。`);
const makeQuestion = (base, index, definition) => ({
  ...base, question_id: `${base.question_id}-v${index}`, target_level: '掌握', question_type: definition.type, difficulty: String(definition.difficulty),
  question_summary: `${base.question_summary}·${definition.type}·v${index}`, prompt: definition.prompt, options_json: JSON.stringify(definition.options), correct_option: String(definition.correct), answer_key: definition.options[definition.correct], explanation: definition.explanation,
  scoring_rule: '单选正确得 1 分', source_note: `${base.source_note}；内容负责人编写的独立${definition.type}题 v${index}`, version: String(index), status: 'approved'
});
const fixedBases = baseRows.map(base => {
  const fix = baseFixes[base.question_id];
  return fix ? { ...base, question_type: fix.type, difficulty: String(fix.difficulty), prompt: fix.prompt, options_json: JSON.stringify(fix.options), correct_option: String(fix.correct), answer_key: fix.options[fix.correct], explanation: fix.explanation } : base;
});
const independentRows = fixedBases.flatMap(base => variants[base.question_id].map((definition, offset) => makeQuestion(base, offset + 2, definition)));
const allRows = [...fixedBases, ...independentRows];
const questionIds = new Set(allRows.map(row => row.question_id));
const copyEdges = file => ({ ...file, rows: [...file.rows.filter(row => !isVariant(row.question_id)), ...independentRows.flatMap(question => {
  const origin = question.question_id.replace(/-v\d+$/, '');
  return file.rows.filter(row => row.question_id === origin && !isVariant(row.question_id)).map(row => ({ ...row, question_id: question.question_id }));
})] });
const nextKnowledge = copyEdges(knowledge); const nextAbilities = copyEdges(abilities); const nextSources = copyEdges(sources);
for (const row of [...nextKnowledge.rows, ...nextAbilities.rows, ...nextSources.rows]) if (!questionIds.has(row.question_id)) throw new Error(`边表引用不存在的题目：${row.question_id}`);
const nextBlueprints = { ...blueprints, rows: blueprints.rows.map(blueprint => ({ ...blueprint, current_approved_versions: String([...new Set(nextKnowledge.rows.filter(edge => edge.knowledge_point_id === blueprint.knowledge_point_id && questionIds.has(edge.question_id)).map(edge => edge.question_id))].length), gap_status: 'review_required', owner_action: '独立题已写入；需运行题库质量审核并由内容负责人填写人工校准结果。' })) };
const optionKey = row => JSON.parse(row.options_json).map(value => value.trim()).sort().join('|');
for (const row of independentRows) {
  const base = fixedBases.find(item => item.question_id === row.question_id.replace(/-v\d+$/, ''));
  if (optionKey(row) === optionKey(base)) throw new Error(`${row.question_id} 仍复用了基础题选项`);
  if (/^(应用情境：|综合判断：)/.test(row.prompt)) throw new Error(`${row.question_id} 使用了通用题干`);
}
if (new Set(allRows.map(row => row.prompt)).size !== allRows.length) throw new Error('存在重复题干');
console.log(`预览：${fixedBases.length} 道基础题，${independentRows.length} 道独立掌握题，共 ${allRows.length} 道；所有新增题均为不同选项和具体情境。`);
if (apply) {
  await mkdir(SNAPSHOT, { recursive: true });
  let hasOriginalSnapshot = true;
  try { await access(resolve(SNAPSHOT, 'question_bank.csv')); } catch { hasOriginalSnapshot = false; }
  if (!hasOriginalSnapshot) await Promise.all([
      writeFile(resolve(SNAPSHOT, 'question_bank.csv'), csv(bank.headers, bank.rows), 'utf8'),
      writeFile(resolve(SNAPSHOT, 'question_knowledge_edges.csv'), csv(knowledge.headers, knowledge.rows), 'utf8'),
      writeFile(resolve(SNAPSHOT, 'question_ability_edges.csv'), csv(abilities.headers, abilities.rows), 'utf8'),
      writeFile(resolve(SNAPSHOT, 'question_source_edges.csv'), csv(sources.headers, sources.rows), 'utf8'),
      writeFile(resolve(SNAPSHOT, 'question_blueprint_catalog.csv'), csv(blueprints.headers, blueprints.rows), 'utf8'),
    ]);
  await Promise.all([
    save('question_bank.csv', { ...bank, rows: allRows }), save('question_knowledge_edges.csv', nextKnowledge), save('question_ability_edges.csv', nextAbilities), save('question_source_edges.csv', nextSources), save('question_blueprint_catalog.csv', nextBlueprints),
  ]);
  console.log(`已写入独立题库；原题库快照保存在 ${SNAPSHOT}`);
}
