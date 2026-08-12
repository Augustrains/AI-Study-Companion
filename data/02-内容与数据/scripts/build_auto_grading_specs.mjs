#!/usr/bin/env node
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dataDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'data');
const out = join(dataDir, 'mastery_task_auto_grading_spec.csv');
const csv = value => `"${String(value ?? '').replaceAll('"', '""')}"`;
const field = (id, label, type, answer, points, options = []) => ({ id, label, type, options, answer, points });
const enumField = (id, label, value, points, options) => field(id, label, 'enum', { value }, points, options);
const numberField = (id, label, value, points, tolerance = 0.0001) => field(id, label, 'number', { value, tolerance }, points);
const textField = (id, label, value, points) => field(id, label, 'text', { value }, points);
const setField = (id, label, values, points, minCorrect = values.length) => field(id, label, 'set', { values, minCorrect }, points, values);
const orderedField = (id, label, values, points) => field(id, label, 'ordered', { values }, points, values);

if (existsSync(out) && !process.argv.includes('--force')) {
  throw new Error('自动判分规格已存在。为保护内容负责人的答案键修改，默认不会覆盖；只有确实需要重建时才使用 --force。');
}

// 每项均是固定字段，而不是让模型解释一段自由文字。题目内容负责人可在不改服务代码的前提下修改答案键。
const specs = [
  ['mt-rl-discount', '折扣因子决策解释', [enumField('immediate_gamma', '即时奖励优先时的 gamma', 'small', 2, ['small', 'large']), enumField('long_term_gamma', '长期回报优先时的 gamma', 'large', 2, ['small', 'large'])]],
  ['mt-math-prob', '三步回报推导', [numberField('term_1', '第 1 项', 2, 1), numberField('term_2', '第 2 项', 1.5, 1), numberField('term_3', '第 3 项', 1.25, 1), numberField('return_value', '折扣回报', 4.75, 1)]],
  ['mt-algo-dp', '价值迭代更新诊断', [setField('missing_parts', '原式缺少的部分', ['discount_factor', 'next_state_value'], 2), enumField('update_structure', '正确更新结构', 'reward + gamma * max_next_value', 2, ['reward + gamma * max_next_value', 'reward_only', 'gamma * current_value'])]],
  ['mt-rl-bellman', '贝尔曼更新计算', [numberField('discounted_future', '折扣后的未来价值', 6, 2), numberField('target_value', '动作价值目标', 7, 2)]],
  ['mt-rl-mdp', '网格机器人 MDP', [enumField('state', '状态定义', 'grid_position', 1, ['grid_position', 'robot_color', 'episode_number']), enumField('action', '动作定义', 'move_direction', 1, ['move_direction', 'reward_value', 'next_state']), enumField('reward', '奖励定义', 'reach_goal_reward', 1, ['reach_goal_reward', 'current_position', 'action_name']), enumField('transition', '不确定性示例', 'slip_to_neighbor', 1, ['slip_to_neighbor', 'always_same_state', 'reward_is_random'])]],
  ['mt-rl-qlearning', 'Q 表更新函数', [enumField('non_terminal_target', '非终止状态目标值', 'reward + gamma * max_next_q', 2, ['reward + gamma * max_next_q', 'reward + max_current_q', 'gamma * current_q']), enumField('terminal_future', '终止状态未来价值', 'zero', 1, ['zero', 'max_next_q', 'current_q']), enumField('update_rule', '更新形式', 'q + alpha * (target - q)', 1, ['q + alpha * (target - q)', 'target - q', 'q + target'])]],
  ['mt-ml-task', '任务类型辨析', [enumField('house_price', '房价预测', 'regression_continuous_label', 1, ['regression_continuous_label', 'classification_category_label', 'clustering_no_label']), enumField('spam', '垃圾邮件识别', 'classification_category_label', 1, ['regression_continuous_label', 'classification_category_label', 'clustering_no_label']), enumField('user_grouping', '用户分群', 'clustering_no_label', 1, ['regression_continuous_label', 'classification_category_label', 'clustering_no_label']), enumField('label_rule', '聚类的标签特点', 'no_predefined_label', 1, ['no_predefined_label', 'continuous_label', 'binary_label'])]],
  ['mt-ml-paradigm', '训练验证测试分工', [enumField('train', '训练集用途', 'fit_parameters', 1, ['fit_parameters', 'select_hyperparameters', 'final_evaluation']), enumField('validation', '验证集用途', 'select_hyperparameters', 1, ['fit_parameters', 'select_hyperparameters', 'final_evaluation']), enumField('test', '测试集用途', 'final_evaluation', 1, ['fit_parameters', 'select_hyperparameters', 'final_evaluation']), enumField('test_leakage', '反复用测试集调参的后果', 'overestimate_generalization', 1, ['overestimate_generalization', 'reduce_training_loss', 'increase_data_size'])]],
  ['mt-ml-regression', '二手车价格建模', [enumField('label', '预测标签', 'continuous_price', 1, ['continuous_price', 'car_brand_category', 'cluster_id']), setField('features', '选择 3 个特征', ['age', 'mileage', 'brand'], 2, 3), enumField('reason', '属于回归的原因', 'continuous_target', 1, ['continuous_target', 'no_label', 'binary_target'])]],
  ['mt-ml-linear-regression', '批量线性预测', [textField('formula', '预测公式', 'X @ w + b', 2), enumField('x_shape', 'X 的形状', 'batch_size x d', 1, ['batch_size x d', 'd x batch_size', 'batch_size x 1']), enumField('prediction_shape', '预测值形状', 'batch_size x 1', 1, ['batch_size x 1', 'd x 1', '1 x batch_size'])]],
  ['mt-ml-logistic', '二分类阈值错误', [enumField('positive_rule', '正确的正类判断', 'p >= 0.5', 2, ['p >= 0.5', 'p < 0.5', 'p = 0']), enumField('error_type', '原规则的问题', 'labels_reversed', 2, ['labels_reversed', 'threshold_too_high', 'probability_not_normalized'])]],
  ['mt-ml-loss', '均方误差推导', [numberField('squared_error_1', '第一个样本平方误差', 1, 1), numberField('squared_error_2', '第二个样本平方误差', 4, 1), numberField('mse', '均方误差', 2.5, 1), enumField('training_role', '损失用于训练的作用', 'optimization_signal', 1, ['optimization_signal', 'data_label', 'network_layer'])]],
  ['mt-ml-gradient', '梯度更新方向', [numberField('new_parameter', '更新后的参数', 3.4, 2), enumField('direction', '梯度下降方向', 'subtract_gradient', 2, ['subtract_gradient', 'add_gradient', 'multiply_gradient'])]],
  ['mt-ml-classification', '医疗筛查指标选择', [enumField('metric', '应优先关注的指标', 'recall', 2, ['precision', 'recall', 'accuracy']), enumField('meaning', '该指标的含义', 'true_positive_rate', 2, ['true_positive_rate', 'predicted_positive_precision', 'true_negative_rate'])]],
  ['mt-ml-clustering', '用户聚类解释', [setField('features', '选择两个可量化特征', ['purchase_frequency', 'average_order_value'], 2, 2), enumField('cluster_meaning', '聚类解释', 'behavior_segment', 2, ['behavior_segment', 'ground_truth_label', 'random_group'])]],
  ['mt-ml-ensemble', 'Bagging 与 Boosting 选择', [enumField('bagging', 'Bagging 训练方式', 'parallel_bootstrap', 2, ['parallel_bootstrap', 'sequential_hard_examples', 'single_model']), enumField('boosting', 'Boosting 训练方式', 'sequential_hard_examples', 2, ['parallel_bootstrap', 'sequential_hard_examples', 'single_model'])]],
  ['mt-ml-model-selection', '验证曲线决策', [enumField('selected_model', '应选择的模型', 'model_b', 2, ['model_a', 'model_b']), enumField('reason', '选择依据', 'higher_validation_lower_gap', 2, ['higher_validation_lower_gap', 'higher_training_only', 'more_parameters'])]],
  ['mt-dl-linear-algebra', '矩阵形状与乘法', [enumField('shape', '2×3 乘以 3×1 的形状', '2x1', 1, ['2x1', '3x3', '1x2']), numberField('row_1_result', '示例 A=[[1,2,3],[4,5,6]], v=[1,0,-1] 的第一项', -2, 1), numberField('row_2_result', '同一示例的第二项', -2, 1), enumField('condition', '矩阵相乘条件', 'inner_dimensions_match', 1, ['inner_dimensions_match', 'outer_dimensions_match', 'all_dimensions_equal'])]],
  ['mt-dl-probability', '分类概率解释', [numberField('probability_sum', '三个输出的总和', 1, 1), enumField('predicted_class', '最高概率的类别', 'class_1', 1, ['class_1', 'class_2', 'class_3']), enumField('certainty', '最高概率的含义', 'not_guaranteed_correct', 2, ['not_guaranteed_correct', 'guaranteed_correct', 'no_prediction'])]],
  ['mt-dl-linear-regression', '线性网络训练步骤', [orderedField('training_order', '训练步骤顺序', ['zero_grad', 'forward', 'loss', 'backward', 'step'], 4)]],
  ['mt-dl-softmax', 'Softmax 概率检查', [numberField('sum', '给定输出的总和', 1.5, 1), enumField('valid', '该输出是否有效', 'invalid', 1, ['valid', 'invalid']), setField('constraints', 'Softmax 的两个约束', ['nonnegative', 'sum_to_one'], 2)]],
  ['mt-dl-mlp', 'MLP 结构设计', [numberField('input_dim', '输入维度', 4, 1), numberField('hidden_dim', '固定隐藏层维度', 8, 1), enumField('activation', '隐藏层激活函数', 'relu', 1, ['relu', 'identity', 'softmax']), numberField('output_dim', '输出维度', 3, 1)]],
  ['mt-dl-generalization', '过拟合补救方案', [setField('actions', '选择两项处理', ['weight_decay', 'early_stopping'], 2, 2), enumField('goal', '这些处理的目标', 'improve_generalization', 2, ['improve_generalization', 'memorize_training_data', 'increase_label_count'])]],
  ['mt-dl-initialization', '初始化对比实验', [setField('signals', '记录两个信号', ['training_loss', 'gradient_norm'], 2, 2), enumField('criterion', '判断标准', 'stable_loss_and_gradients', 2, ['stable_loss_and_gradients', 'highest_initial_loss', 'largest_parameter_count'])]],
  ['mt-dl-convolution', '卷积层配置', [numberField('in_channels', '输入通道数', 3, 1), numberField('out_channels', '输出通道数', 16, 1), numberField('kernel_size', '卷积核尺寸', 3, 1), enumField('channel_meaning', '输出通道含义', 'feature_maps', 1, ['feature_maps', 'input_pixels', 'class_labels'])]],
  ['mt-dl-padding', '卷积尺寸错误', [numberField('padding', '最小填充', 1, 2), numberField('output_size', '输出边长', 32, 1), enumField('formula_condition', '保持尺寸的条件', 'padding_one_stride_one_kernel_three', 1, ['padding_one_stride_one_kernel_three', 'padding_zero_stride_one_kernel_three', 'padding_two_stride_two_kernel_three'])]],
  ['mt-dl-pooling', '池化选择', [numberField('max_value', '窗口 [[1,4],[2,3]] 的最大池化', 4, 1), numberField('average_value', '同一窗口的平均池化', 2.5, 1), enumField('max_rule', '最大池化规则', 'select_maximum', 1, ['select_maximum', 'compute_mean', 'select_minimum']), enumField('avg_rule', '平均池化规则', 'compute_mean', 1, ['select_maximum', 'compute_mean', 'select_minimum'])]],
  ['mt-dl-sequence', '销量时间窗', [enumField('input_window', '输入窗口', 'day_1_to_day_7', 1, ['day_1_to_day_7', 'day_8_only', 'random_7_days']), enumField('target', '预测目标', 'day_8', 1, ['day_8', 'day_1', 'average_all_days']), enumField('shuffle', '是否可随意打乱时间', 'no', 2, ['yes', 'no'])]],
  ['mt-dl-rnn', 'RNN 隐藏状态循环', [textField('update_formula', '隐藏状态更新公式', 'h_t = tanh(W_xh*x_t + W_hh*h_prev + b)', 2), enumField('state_flow', '下一时间步使用什么状态', 'new_hidden_state', 2, ['new_hidden_state', 'initial_hidden_state', 'output_label'])]],
  ['mt-dl-neuron', '神经元前向计算', [numberField('weighted_sum', '加权和', 0, 1), numberField('pre_activation', '加偏置后的输出', 1, 2), enumField('operation_order', '正确计算顺序', 'weighted_sum_then_bias', 1, ['weighted_sum_then_bias', 'bias_then_multiply', 'activation_then_sum'])]],
  ['mt-dl-activation', '激活函数必要性', [enumField('linear_stack', '连续线性层的表达能力', 'still_linear', 2, ['still_linear', 'automatically_nonlinear', 'random']), enumField('relu', 'ReLU 定义', 'max_0_x', 2, ['max_0_x', '1_over_1_plus_exp_neg_x', 'x_squared'])]],
  ['mt-dl-forward', '前向损失顺序', [orderedField('order', '正确顺序', ['forward', 'loss', 'backward'], 3), enumField('reason', '为什么不能先反向', 'loss_required_for_gradients', 1, ['loss_required_for_gradients', 'data_required_for_labels', 'optimizer_required_for_input'])]],
  ['mt-dl-loss', '平方损失计算', [numberField('squared_loss', '平方损失', 9, 2), enumField('role', '损失的作用', 'optimization_signal', 2, ['optimization_signal', 'network_output', 'data_augmentation'])]],
  ['mt-dl-backprop', '链式法则梯度', [numberField('gradient_w', 'dL/dw', -6, 3), enumField('rule', '链式法则操作', 'multiply_derivatives', 1, ['multiply_derivatives', 'add_derivatives', 'divide_derivatives'])]],
  ['mt-dl-training', '训练循环修复', [orderedField('order', '正确训练顺序', ['zero_grad', 'forward', 'loss', 'backward', 'step'], 3), enumField('zero_grad_risk', '缺少 zero_grad 的风险', 'gradient_accumulation', 1, ['gradient_accumulation', 'automatic_regularization', 'smaller_dataset'])]],
  ['mt-prog-python', 'Python 循环与列表', [textField('initializer', '累计变量初始化', 'total = 0', 1), textField('loop', '遍历语句', 'for reward in rewards', 1), textField('update', '累计语句', 'total += reward', 2)]],
  ['mt-prog-qtable', 'Q 表字典更新', [textField('lookup', '状态动作值定位', 'q[state][action]', 1), textField('target', '目标值', 'reward + gamma * max_next_q', 1), textField('update', '更新式', 'q + alpha * (target - q)', 2)]],
];

const taskRows = (await readFile(join(dataDir, 'mastery_task_catalog.csv'), 'utf8')).trim().split(/\r?\n/).slice(1);
const taskIds = new Set(taskRows.map(row => row.split(',')[0]));
if (specs.length !== taskIds.size || specs.some(([taskId]) => !taskIds.has(taskId))) throw new Error('自动判分规格必须与每一道掌握任务一一对应');

const header = ['mastery_task_id', 'title', 'grading_type', 'response_schema_json', 'answer_key_json', 'scoring_rules_json', 'max_score', 'status', 'content_review_status', 'authoring_note'];
const rows = specs.map(([mastery_task_id, title, fields]) => {
  const responseSchema = { type: 'object', additionalProperties: false, required: fields.map(item => item.id), fields: fields.map(({ answer, points, ...rest }) => rest) };
  const answerKey = Object.fromEntries(fields.map(item => [item.id, item.answer]));
  const scoringRules = fields.map(item => ({ field: item.id, points: item.points }));
  return [mastery_task_id, title, 'structured_fields', JSON.stringify(responseSchema), JSON.stringify(answerKey), JSON.stringify(scoringRules), 4, 'approved', 'ai_pre_assessed_pending_human', '开发者维护的确定性答案键；内容负责人应离线核对后再解除题库质量门控。'];
});
await writeFile(out, [header, ...rows].map(row => row.map(csv).join(',')).join('\n') + '\n', 'utf8');
console.log(`已生成 ${rows.length} 道自动判分任务规格：${out}`);
