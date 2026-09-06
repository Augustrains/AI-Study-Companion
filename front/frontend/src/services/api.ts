import { bookLearningDomains, books, getBookContent, type BookId, type DiagnosticQuestion, type LearningTask, type Source } from "../data/mockData";
import { getAuthHeaders, getCurrentUserId } from "./session";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
// Use the backend by default. Set VITE_USE_REAL_API=false only for an explicit
// standalone Mock demonstration.
export const USE_REAL_API = import.meta.env.VITE_USE_REAL_API !== "false";

export type ApiState = "initial" | "loading" | "ready" | "empty" | "submitting" | "success" | "error" | "offline" | "stale";
export type ApiError = { code: string; message: string; requestId?: string; retryable?: boolean; details?: unknown };

/**
 * 书籍目录项。
 * 【后端接入清单】GET /api/books -> { books: BookCatalogItem[] }
 * 前端不再写死书籍列表：接口就绪后新增书籍无需改动前端代码。
 * available=false 的书籍在「选书与目标」中展示为「即将上线」且不可选。
 */
export type BookCatalogItem = {
  id: string;
  title: string;
  shortTitle: string;
  subtitle: string;
  /** 该书覆盖的知识点数量，用于选书卡片展示 */
  knowledgePointCount?: number;
  /** 是否已开放学习，缺省视为已开放 */
  available?: boolean;
};
export type BookCatalog = { books: BookCatalogItem[] };

/**
 * 学习目标。
 * 【后端接入清单】POST /api/learner-goals -> LearnerGoalResult
 */
export type LearnerGoalPayload = { bookId: string; targetLevel: string; dailyMinutes: number; targetDate: string };
export type LearnerGoalResult = {
  goalId: string; bookId: string; targetLevel: string; dailyMinutes: number; targetDate?: string | null; updatedAt?: string;
  /** 保存时是否顺带按新预算重排了在途计划的任务日期（只改日期，无损） */
  rescheduled?: boolean;
  /** 重排后预计多少天完成 */
  estimatedDays?: number | null;
  /** 目标水平变了：任务内容该跟着变，但重新生成会丢进度，所以只提示不自动做 */
  planRefreshSuggested?: boolean;
  diagnosableAbilities?: string[];
};
export type LearnerGoalLookup = { exists: boolean; goal?: LearnerGoalResult };

/**
 * 知识点延伸学习资源（B 站 / YouTube / MOOC / 在线教材）。
 * 【后端接入清单】GET /api/learning-resources?knowledgePointIds=a,b -> ResourceCatalog
 * 不传 knowledgePointIds 时返回全部已收录知识点，供「学习资源」页面浏览。
 * 未收录的知识点返回空列表，前端展示空态，不编造链接。
 */
export type LearningResource = {
  title: string;
  platform: "bilibili" | "youtube" | "coursera" | "edx" | "other" | string;
  url: string;
  language: "zh" | "en" | string;
  kind: "video" | "course" | "article" | string;
  note: string;
};
export type KnowledgePointResources = { knowledgePointId: string; resources: LearningResource[] };
export type ResourceCatalog = { items: KnowledgePointResources[] };

export type DiagnosticStartResult = { diagnosticId: string; questions: DiagnosticQuestion[] };
export type DiagnosticResult = { level: string; accuracy: string; confidence: string; evidence: string; answerPerformance: string; generatedAt: string; relatedScope: string };
export type LearningPlanBook = { id: string; title: string; shortTitle: string };
/**
 * 排课时间预算。后端直接使用用户设定的每日学习分钟数，
 * 再用历史「计划 vs 实际」的中位数比值（paceFactor）折算实际占用。
 * 任务自己的 minutes 始终是 AI 的原始估计，不会被校准值改写。
 */
export type PlanTimeBudget = { dailyMinutes: number; totalMinutes: number; estimatedDays: number; paceFactor: number; adjustedTotalMinutes: number };
export type DailyLearningPlan = { date: string; title: string; reason: string; tasks: LearningTask[] };
export type LearningPlanResult = { book: LearningPlanBook; goal: string; goalLevel: string; tasks: LearningTask[]; dailyPlans?: DailyLearningPlan[]; advice: string[]; resources: Source[]; timeBudget?: PlanTimeBudget };
export type LearningPlanLookup = { exists: boolean; plan: LearningPlanResult | null };
export type ReadingMaterialResult = { item_title: string; integrated_content: string; generated_by: string; references: Array<{ title: string; location: string }>; search_error?: string | null };
export type TodayLearningResponse = {
  book: { id: string; title: string; shortTitle: string; subtitle: string };
  goal: string;
  lastLearned: string;
  weeklyProgress: {
    progressPercent: number;
    completedTaskCount: number;
    totalTaskCount: number;
    studyDurationSeconds: number;
    studyDurationHours: number;
    accuracy: number;
    dailyDuration: Array<{ date: string; durationSeconds: number }>;
  };
  recommendation: { taskId: string; title: string; minutes: number; difficulty: string; reason: string; priority: string } | null;
  knowledgeGraph: { goal: string; nodes: Array<{ id: string; label: string; status: string; accuracy: number | null; masteryScore: number | null; taskId: string | null; reason: string; description: string }> };
  tasks: LearningTask[];
  taskSummary: { completed: number; total: number };
  continueLearning: { taskId: string; title: string; type: string; minutes: number; status: string; expectedCompletionDate: string; description: string; reason: string } | null;
};
/**
 * 后端暂时保留 conversationId 作为接口兼容令牌；问答历史实际按 userId + bookId 管理。
 * resetContext 只在用户明确点击“清空对话”时发送。
 */
export type QaAnswerMode = "direct" | "socratic";
export type QaContextResult = {
  conversationId: string;
  bookId: BookId;
  userId: string;
  createdAt: string;
  status: string;
  answerMode?: QaAnswerMode;
  learningTaskId?: string | null;
  socraticState?: string | null;
};
/**
 * allowGeneralFallback：资料检索不足以回答时，是否允许改用通用模型作答。
 * 默认 false —— 必须由用户在界面上显式确认后才置为 true，避免无出处的答案被当成教材依据。
 * 【后端接入清单】POST /rag/conversations/{id}/messages 需接收该字段，
 * 并在降级作答时返回 answeredByGeneralModel=true、citations=[]。
 */
export type QaQuestionPayload = { bookId: BookId; question: string; conversationId?: string; sources?: Source[]; allowGeneralFallback?: boolean; answerMode?: QaAnswerMode; learningTaskId?: string | null; attachment?: File };
export type QaAttachment = { id: number; messageId: number; fileName: string; fileType: string; fileSize: number; fileUrl: string; createdAt: string; updatedAt: string };
export type QaResult = {
  answer: string;
  refused: boolean;
  citations: Source[];
  relatedKnowledgePoints?: string[];
  recommendedAction?: string;
  conversationId?: string;
  requestId?: string;
  answeredByGeneralModel?: boolean;
  answerMode?: QaAnswerMode;
  learningTaskId?: string | null;
  socraticState?: string | null;
  responseQuality?: string | null;
  socraticCompleted?: boolean;
  userMessageId?: number | null;
};
export type MaterialLearningPlanPayload = { bookId: BookId; title: string; goal: string; description: string; minutes: number; expectedCompletionDate: string; resources: Source[] };
export type LearningActivity = {
  id: string;
  userId: string;
  category: "profile" | "task" | "diagnostic" | "qa";
  activityType: string;
  status: string;
  title: string;
  description: string;
  occurredAt: string;
  createdAt: string;
  updatedAt: string;
  bookId?: string | null;
  planId?: string | null;
  taskId?: string | null;
  knowledgePointIds: string[];
  result: Record<string, unknown>;
  detail: Record<string, unknown>;
};
export type LearningActivityList = { records: LearningActivity[]; total: number; page: number; pageSize: number; hasNext: boolean };
export type LearningRecordSummary = {
  today: { activityCount: number; completedTasks: number; studyMinutes: number; diagnosticAccuracy: number | null };
  calendar: Array<{ date: string; activityCount: number; completedTasks: number; studyMinutes: number }>;
};
export type LearningActivityList = { records: LearningActivity[]; total: number; page: number; pageSize: number; hasNext: boolean; summary?: LearningRecordSummary };
export type LearnerPreferences = {
  activity_types: string[];
  content_style: string;
  difficulty: string;
  session_duration_minutes: number;
  learning_frequency: string;
};
export type LearnerProfile = {
  user_id: string;
  learning_domain: string;
  background: string;
  self_assessed_level: string;
  known_knowledge_point_ids: string[];
  known_knowledge_point_note: string;
  unknown_knowledge_point_ids: string[];
  current_confusions: string;
  additional_requirements: string;
  preferences: LearnerPreferences;
};
export type LearnerProfilePayload = Omit<LearnerProfile, "preferences"> & { preferences: LearnerPreferences };
export type LearnerProfileResult = { exists: boolean; profile: LearnerProfile | null };
export type KnowledgePoint = { id: string; name: string; description: string };
export type KnowledgePointResult = { learningDomain: string; knowledgePoints: KnowledgePoint[] };
export type LearnerProfileWorkflowStart = { workflowId: string; status: "pending_confirmation"; draft: LearnerProfile; allowedActions: Array<"approve" | "edit" | "reject"> };

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  // 资料问答可能顺序执行查询改写和答案生成两次 LLM 调用。服务端每次
  // 调用的预算是 120 秒，不能沿用普通交互的 15 秒预算，否则浏览器会
  // 在服务端仍正常工作时主动中止请求。
  const timeoutMs = path.includes("/learning-plans/weekly/generate")
    ? 120000
    // RAG 请求包含检索及 LLM 生成，前端路径经过 Vite 代理后为 /api/rag，
    // 但这里传入 request 的是去掉 /api 前缀的 /rag/... 路径。
    : path.startsWith("/rag/")
      ? 270000
    : path === "/diagnostics/start"
      ? 45000
      // 重建学习画像会依次调用目标分析和掌握度分析智能体，
      // 保存接口不能使用普通读请求的 15 秒超时。
      : path === "/learner-profile/setup" && init?.method === "POST"
        ? 120000
      : path.includes("/learner-calibrations")
        ? 120000
        : 15000;
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...getAuthHeaders(), ...init?.headers },
      headers: { "Content-Type": "application/json", ...getAuthHeaders(), ...init?.headers },
      signal: controller.signal,
      ...init,
    });
    if (!response.ok) {
      const error = (await response.json().catch(() => null)) as ApiError | null;
      throw error ?? { code: `HTTP_${response.status}`, message: "请求失败", retryable: response.status >= 500 };
    }
    return response.status === 204 ? (undefined as T) : (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw { code: "REQUEST_TIMEOUT", message: "请求超时，请检查服务是否正常运行。", retryable: true } satisfies ApiError;
    }
    if (error && typeof error === "object" && "code" in error) throw error;
    throw { code: "NETWORK_ERROR", message: "网络暂时不可用，请稍后重试。", retryable: true } satisfies ApiError;
  } finally {
    window.clearTimeout(timeout);
  }
}

const wait = (duration = 420) => new Promise((resolve) => window.setTimeout(resolve, duration));

/**
 * 页面演示使用的模拟服务。它与真实接口保持同一组动作名称，后端接入时只替换服务实现。
 */
// 纯前端模式下的目标存档，让「保存后再打开」能读回同一份，行为和真实后端一致。
const mockGoals = new Map<string, LearnerGoalResult>();

export const mockApi = {
  async getBooks(): Promise<BookCatalog> {
    await wait(200);
    // 模拟服务不编造知识点数量：knowledgePointCount 留空，由页面显示为「—」。
    return {
      books: [
        ...books.map((book) => ({ ...book, available: true })),
        { id: "rl", title: "《强化学习》", shortTitle: "强化学习", subtitle: "马尔可夫决策过程与 Q 学习", available: false },
      ],
    };
  },
  async getLearningResources(knowledgePointIds?: string[]): Promise<ResourceCatalog> {
    await wait(200);
    // 模拟服务内置与后端资源文件一致的几条真实链接，保证断网/纯前端演示时也能点开。
    const catalog: Record<string, LearningResource[]> = {
      "kp-ml-intro": [
        { title: "[中英字幕]吴恩达机器学习系列课程", platform: "bilibili", url: "https://www.bilibili.com/video/BV164411b7dx/", language: "zh", kind: "course", note: "前几集覆盖机器学习定义与监督/无监督学习。" },
        { title: "A Gentle Introduction to Machine Learning", platform: "youtube", url: "https://www.youtube.com/watch?v=Gv9_4yMHFhI", language: "en", kind: "video", note: "StatQuest 图解机器学习基本术语，零基础友好。" },
      ],
      "kp-ml-logistic-regression": [
        { title: "StatQuest: Logistic Regression", platform: "youtube", url: "https://www.youtube.com/watch?v=yIYKR4sgzI8", language: "en", kind: "video", note: "讲清与线性回归的区别、sigmoid 与最大似然估计。" },
        { title: "Logistic Regression · Google", platform: "other", url: "https://developers.google.com/machine-learning/crash-course/logistic-regression", language: "en", kind: "article", note: "覆盖 sigmoid 概率输出、对数损失与正则化。" },
      ],
      "kp-ml-kmeans": [
        { title: "StatQuest: K-means clustering", platform: "youtube", url: "https://www.youtube.com/watch?v=4b5d3muPQmA", language: "en", kind: "video", note: "分步动画演示迭代过程，并讲肘部法选 K。" },
        { title: "动手学机器学习 · 第14章 k均值聚类", platform: "other", url: "https://hml.boyuai.com/books/chapter14", language: "zh", kind: "article", note: "上海交大中文教材章节，含 NumPy 实现。" },
      ],
    };
    const wanted = knowledgePointIds?.length ? knowledgePointIds : Object.keys(catalog);
    return { items: wanted.map((id) => ({ knowledgePointId: id, resources: catalog[id] ?? [] })) };
  },
  async saveLearnerGoal(payload: LearnerGoalPayload): Promise<LearnerGoalResult> {
    await wait(420);
    mockGoals.set(payload.bookId, { goalId: `goal-${payload.bookId}`, ...payload, updatedAt: new Date().toISOString() });
    return mockGoals.get(payload.bookId)!;
  },
  async getLearnerGoal(bookId: string): Promise<LearnerGoalLookup> {
    await wait(160);
    const goal = mockGoals.get(bookId);
    return goal ? { exists: true, goal } : { exists: false };
  },
  async initializeQaContext(bookId: BookId, _resetContext = false): Promise<QaContextResult> {
    await wait(260);
    return { conversationId: `mock-qa-${Date.now()}`, bookId, userId: getCurrentUserId(), createdAt: new Date().toISOString(), status: "active" };
  },
  async finishQaLearningTask(_bookId: BookId, _learningTaskId: string): Promise<{ completed: boolean }> {
    await wait(120);
    return { completed: true };
  },
  async startDiagnostic(bookId: BookId, _learningGoal?: string, _planDayId?: string, _planItemId?: string): Promise<DiagnosticStartResult> {
    await wait();
    return { diagnosticId: `demo-${bookId}-diagnostic`, questions: getBookContent(bookId).questions };
  },
  async submitDiagnosticAnswer(diagnosticId: string, payload: { questionId: string; answer: string; skipped?: boolean }) {
    await wait(260);
    return { diagnosticId, ...payload, saved: true };
  },
  async finishDiagnostic(diagnosticId: string): Promise<DiagnosticResult> {
    await wait(520);
    return {
      level: "中等偏上",
      accuracy: "75%",
      confidence: "高",
      evidence: "本次作答结果和知识点表现是主要判断依据。",
      answerPerformance: "本次诊断共完成 4 道题，整体表现稳定。",
      generatedAt: new Date().toISOString(),
      relatedScope: "当前学习目标及其前置知识点。",
    };
  },
  async submitCalibration(payload: { diagnosticId: string; level: string; reason: string }) {
    await wait(420);
    return { calibrationId: `calibration-${Date.now()}`, ...payload, saved: true };
  },
  async generatePlan(payload: { diagnosticId: string; bookId: BookId; goal: string }): Promise<LearningPlanResult> {
    await wait(520);
    const book = books.find((item) => item.id === payload.bookId) ?? books[0];
    return {
      book: { id: book.id, title: book.title, shortTitle: book.shortTitle },
      goal: payload.goal,
      goalLevel: "",
      tasks: [],
      advice: [],
      resources: [],
    };
  },
  async generateWeeklyPlan(bookId: BookId, _reason = ""): Promise<LearningPlanResult> {
    return mockApi.generatePlan({ diagnosticId: `mock-${bookId}`, bookId, goal: getBookContent(bookId).goal });
  },
  async createMaterialPlan(payload: MaterialLearningPlanPayload): Promise<LearningPlanResult> {
    await wait(520);
    const book = books.find((item) => item.id === payload.bookId) ?? books[0];
    return {
      book: { id: book.id, title: book.title, shortTitle: book.shortTitle },
      goal: payload.goal,
      goalLevel: "自定义学习目标",
      tasks: [{ id: `material-${Date.now()}`, title: payload.title, type: "资料问答", minutes: payload.minutes, status: "todo", reason: "基于资料问答来源创建", description: payload.description, expectedCompletionDate: payload.expectedCompletionDate, knowledgePointIds: [] }],
      advice: ["建议先阅读关联教材，再回到资料问答中进行复习和追问。"],
      resources: payload.resources,
    };
  },
  async getLearningPlan(): Promise<LearningPlanLookup> {
    await wait(180);
    return { exists: false, plan: null };
  },
  async getReadingMaterials(_bookId: BookId, itemTitle: string): Promise<ReadingMaterialResult> {
    await wait(300);
    return {
      item_title: itemTitle,
      integrated_content: `${itemTitle}\n\n这是根据当前学习任务整理的阅读讲义。请先阅读核心概念，再结合示例完成后续练习。\n\n教材内容：当前模拟服务未连接教材正文。切换到真实服务后，将展示教材与网络资料的整合内容。`,
      generated_by: "mock",
      references: [],
    };
  },
  async getTodayLearning(bookId: BookId): Promise<TodayLearningResponse> {
    await wait(180);
    const content = getBookContent(bookId);
    return {
      book: books.find((book) => book.id === bookId) ?? books[0],
      goal: content.goal,
      lastLearned: content.lastLearned,
      // 模拟服务按自身任务状态算出统计，避免与任务列表显示的完成数对不上。
      weeklyProgress: (() => {
        const completed = content.todayTasks.filter((task) => task.status === "completed").length;
        const total = content.todayTasks.length;
        const seconds = content.todayTasks.filter((task) => task.status === "completed").reduce((sum, task) => sum + task.minutes * 60, 0);
        return {
          progressPercent: total ? Math.round((completed / total) * 100) : 0,
          completedTaskCount: completed,
          totalTaskCount: total,
          studyDurationSeconds: seconds,
          studyDurationHours: Math.round((seconds / 3600) * 10) / 10,
          accuracy: completed ? 78 : 0,
          dailyDuration: [4, 3, 2, 1, 0].map((daysAgo) => ({ date: new Date(Date.now() - daysAgo * 86400000).toISOString().slice(0, 10), durationSeconds: Math.round(seconds / 5) })),
        };
      })(),
      recommendation: null,
      knowledgeGraph: { goal: content.goal, nodes: content.nodes.map((node) => ({ id: node.label, label: node.label, status: node.tone, accuracy: null, masteryScore: null, taskId: null, reason: "", description: node.description })) },
      tasks: content.todayTasks,
      taskSummary: { completed: 0, total: content.todayTasks.length },
      continueLearning: (() => {
        const task = content.todayTasks.find((item) => item.status === "in_progress") ?? content.todayTasks.find((item) => item.status === "todo");
        return task ? { taskId: task.id, title: task.title, type: task.type, minutes: task.minutes, status: task.status, expectedCompletionDate: new Date().toISOString().slice(0, 10), description: task.description, reason: task.reason } : null;
      })(),
    };
  },
  async writeLearningEvent(payload: { taskId: string; eventType: string; status: string; durationSeconds?: number; plannedMinutes?: number }) {
  async writeLearningEvent(payload: { taskId: string; eventType: string; status: string; bookId?: BookId; durationSeconds?: number; plannedMinutes?: number }) {
    await wait(260);
    return { eventId: `event-${Date.now()}`, ...payload, saved: true };
  },
  async completeLearningPlanItem(_itemId: string) { await wait(120); return { completed: true }; },
  async startLearningPlanItem(_itemId: string) { await wait(120); return { started: true }; },
  async executeCode(_code: string, _tests: string[]) {
    await wait(120);
    return { passed: true, stdout: "", stderr: "", timed_out: false };
  },
  async getCodeTaskContent(_itemId: string) {
    await wait(120);
    return { kind: "coding", prompt: "情景：你正在为数据处理服务实现一个小工具。请根据函数签名完成代码，处理正常输入和边界情况，不修改原始输入，并通过下面的测试用例。", starter_code: "def solve(values):\n    # 返回处理结果\n    pass\n", tests: ["assert solve([]) == []", "assert solve([3, 1, 2]) == [1, 2, 3]"] };
  },
  async getLearningRecords(_params?: { category?: string; startDate?: string; endDate?: string; page?: number; pageSize?: number }): Promise<LearningActivityList> {
    await wait(260);
    return { records: [], total: 0, page: 1, pageSize: 50, hasNext: false };
  },
  async askQuestion(payload: QaQuestionPayload & { sources: Source[] }): Promise<QaResult> {
    await wait(720);
    if (payload.question.includes("接口失败")) throw { code: "QA_TEMPORARY_ERROR", message: "资料问答暂时不可用，请稍后重试。", retryable: true } satisfies ApiError;
    // 演示拒答与通用模型降级：问题含「资料外」时模拟检索不到依据。
    if (payload.question.includes("资料外")) {
      if (!payload.allowGeneralFallback) {
        return { answer: "当前教材资料中没有找到能够支持该问题的内容。", refused: true, citations: [] };
      }
      return { answer: "（通用模型回答）这个问题超出了当前教材范围，以下内容来自通用知识，未经教材核对，请谨慎参考。", refused: false, citations: [], answeredByGeneralModel: true };
    }
    if (payload.answerMode === "socratic") {
      return {
        answer: "我们先不急着看完整答案。你认为这道题首先需要明确的核心概念是什么？",
        refused: false,
        citations: payload.sources,
        answerMode: "socratic",
        learningTaskId: payload.learningTaskId ?? `task-${Date.now()}`,
        socraticState: "probe",
      };
    }
    return { answer: "这是一个很好的追问。建议先从定义、输入条件和输出结果三个角度拆解，再结合引用资料核对关键概念。", refused: false, citations: payload.sources, answerMode: "direct" };
  },
  async listQaAttachments(_messageId: number): Promise<QaAttachment[]> {
    return [];
  },
  async getLearnerProfile(userId: string, learningDomain: string): Promise<LearnerProfileResult> {
    await wait(260);
    return { exists: false, profile: null };
  },
  async getKnowledgePoints(_learningDomain: string): Promise<KnowledgePointResult> {
    return { learningDomain: _learningDomain, knowledgePoints: [] };
  },
  async saveLearnerProfile(payload: LearnerProfilePayload): Promise<LearnerProfileResult> {
    await wait(420);
    return { exists: true, profile: payload };
  },
};

type WeeklyPlanItem = { id?: number; title: string; description?: string; status?: LearningTask["status"]; source?: string; item_type?: string; adaptive_reason?: string; minutes?: number; knowledge_point_id?: number };
type WeeklyPlanDay = { id?: number; expected_date?: string; date?: string; title?: string; adaptive_reason?: string; items?: WeeklyPlanItem[] };
type WeeklyPlanPayload = { planId?: number; book?: { id: number; book_name?: string }; goal?: { goal?: string; aim_level?: number } | string; days?: WeeklyPlanDay[]; advice?: string[]; resources?: Source[]; plan?: { goal?: string; days?: WeeklyPlanDay[] } };

const databaseBookId: Record<string, number> = { ml: 2, dl: 1 };

function planMinutes(item: WeeklyPlanItem): number {
  if (item.minutes !== undefined) return item.minutes;
  const match = `${item.title} ${item.description ?? ""}`.match(/(\d+)\s*(?:分钟|min)/i);
  return match ? Number(match[1]) : 0;
}

function asLearningPlan(payload: WeeklyPlanPayload, bookId: BookId): LearningPlanResult {
  const source = payload.days ? payload : payload.plan ?? {};
  const book = books.find((item) => item.id === bookId) ?? books[0];
  const goal = typeof payload.goal === "string" ? payload.goal : payload.goal?.goal ?? payload.plan?.goal ?? "";
  const dailyPlans = (source.days ?? []).map((day) => {
    const items = day.items ?? [];
    const dayTasks = items.map((item, index) => ({
      id: String(item.id ?? `${day.expected_date ?? day.date ?? "day"}-${index}`),
      title: item.title,
      type: item.item_type === "diagnostic" || item.source === "review_due" ? "能力诊断" : item.item_type === "reading" ? "阅读" : item.item_type === "review" || item.source === "spaced_review" ? "复习" : item.item_type === "practice" ? "练习" : item.item_type === "coding" ? "编程实践" : "针对性学习",
      minutes: planMinutes(item),
      status: item.status ?? "todo",
      reason: item.adaptive_reason ?? "",
      description: item.description ?? "",
      expectedCompletionDate: day.expected_date ?? day.date ?? "",
      knowledgePointIds: item.knowledge_point_id ? [String(item.knowledge_point_id)] : [],
      planDayId: day.id ? String(day.id) : undefined,
    }));
    return {
      date: day.expected_date ?? day.date ?? "",
      title: day.title ?? "当日学习计划",
      reason: day.adaptive_reason ?? "根据当前掌握度与每日时长生成。",
      tasks: dayTasks,
    };
  });
  const tasks = dailyPlans.flatMap((day) => day.tasks);
  const readingTitles = tasks.filter((task) => task.type === "阅读").map((task) => task.title).filter((title, index, list) => list.indexOf(title) === index);
  const resources = payload.resources?.length ? payload.resources : readingTitles.slice(0, 5).map((title, index) => ({ id: `plan-reading-${index + 1}`, type: "教材", title: title.replace(/^阅读：/, ""), location: "对应教材章节", excerpt: "本周计划中的重点阅读材料。" }));
  const advice = payload.advice?.length ? payload.advice : ["建议每天先完成诊断，再按“阅读—复习—练习”的顺序学习，逐步巩固本周重点。"];
  return { book: { id: book.id, title: book.title, shortTitle: book.shortTitle }, goal, goalLevel: "", tasks, dailyPlans, advice, resources };
}

type MySqlProfileSetup = {
  exists: boolean;
  profile: {
    background: string;
    preferred_content_style: string;
    preferred_difficulty?: string;
    learning_frequency?: string;
    self_assessed_level?: string;
    current_confusions?: string;
    additional_requirements?: string;
    preferred_activity_types?: string[];
    session_duration_minutes?: number | null;
  } | null;
};

// The UI keeps stable short book keys while MySQL stores `books.id`.
const profileBookMapping: Record<string, { uiBookId: string; databaseBookId: number }> = {
  machine_learning: { uiBookId: "ml", databaseBookId: 2 },
  deep_learning: { uiBookId: "dl", databaseBookId: 1 },
  ml: { uiBookId: "ml", databaseBookId: 2 },
  dl: { uiBookId: "dl", databaseBookId: 1 },
};

const aimLevelByTarget: Record<string, number> = {
  "能够复述核心概念": 0,
  "能够独立完成基础练习": 1,
  "能够解决进阶应用问题": 2,
  "能够指导他人 / 应对面试": 3,
};

function profileBookFor(learningDomain: string) {
  const mapped = profileBookMapping[learningDomain];
  if (!mapped) throw { code: "UNSUPPORTED_BOOK", message: "当前书籍尚未映射到数据库课程。", retryable: false } satisfies ApiError;
  return mapped;
}

function asLearnerProfile(response: MySqlProfileSetup, userId: string, learningDomain: string): LearnerProfileResult {
  if (!response.exists || !response.profile) return { exists: false, profile: null };
  const profile = response.profile;
  return {
    exists: true,
    profile: {
      user_id: userId,
      learning_domain: learningDomain,
      background: profile.background,
      self_assessed_level: profile.self_assessed_level ?? "unknown",
      known_knowledge_point_ids: [],
      known_knowledge_point_note: "",
      unknown_knowledge_point_ids: [],
      current_confusions: profile.current_confusions ?? "",
      additional_requirements: profile.additional_requirements ?? "",
      preferences: {
        activity_types: profile.preferred_activity_types ?? [],
        content_style: profile.preferred_content_style ?? "balanced",
        difficulty: profile.preferred_difficulty ?? "adaptive",
        session_duration_minutes: profile.session_duration_minutes ?? 30,
        learning_frequency: profile.learning_frequency ?? "flexible",
      },
    },
  };
}

/**
 * 真实服务的接口映射。启用 VITE_USE_REAL_API=true 后，页面可以切换到后端。
 */
export const realApi = {
  /**
   * 书籍目录：后端 GET /books 就绪前自动回退到本地目录，
   * 保证「选书与目标」页面在任何阶段都可用。接口上线后无需改前端。
   */
  getBooks: async (): Promise<BookCatalog> => {
    try {
      return await request<BookCatalog>("/books");
    } catch {
      // /books 未就绪：回退本地目录，并用已有的知识点接口补齐真实数量（取不到就留空，不编造）。
      const catalog = await mockApi.getBooks();
      const enriched = await Promise.all(catalog.books.map(async (book) => {
        const domain = bookLearningDomains[book.id];
        if (!domain || book.available === false) return book;
        try {
          const result = await request<KnowledgePointResult>(`/learner-profile/knowledge-points?learning_domain=${encodeURIComponent(domain)}`);
          return { ...book, knowledgePointCount: result.knowledgePoints.length };
        } catch {
          return book;
        }
      }));
      return { books: enriched };
    }
  },
  getLearningResources: async (knowledgePointIds?: string[]): Promise<ResourceCatalog> => {
    const query = knowledgePointIds?.length ? `?knowledgePointIds=${encodeURIComponent(knowledgePointIds.join(","))}` : "";
    try {
      return await request<ResourceCatalog>(`/learning-resources${query}`);
    } catch {
      return mockApi.getLearningResources(knowledgePointIds);
    }
  },
  /**
   * 保存学习目标。
   * 这里**不做降级**：写操作失败必须让用户看见。
   * 原来的 catch → mock 让「后端没这个接口」和「保存成功」在界面上长得一模一样，
   * 用户改完目标看到成功提示，服务端其实什么都没发生。降级只用于读接口。
   */
  saveLearnerGoal: (payload: LearnerGoalPayload): Promise<LearnerGoalResult> =>
    request<LearnerGoalResult>("/learner-goals", { method: "POST", body: JSON.stringify({ ...payload, userId: getCurrentUserId() }) }),

  /** 读回已保存的目标，供「选书与目标」页回填；没设过时返回 exists:false。 */
  getLearnerGoal: async (bookId: string): Promise<LearnerGoalLookup> => {
    try {
      const query = new URLSearchParams({ userId: getCurrentUserId(), bookId });
      return await request<LearnerGoalLookup>(`/learner-goals?${query.toString()}`);
    } catch {
      // 读接口可以降级：拿不到就当作没设过，页面用默认值起步。
      return { exists: false };
    }
  },
  initializeQaContext: (bookId: BookId, resetContext = false) => request<QaContextResult>("/rag/conversations", {
    method: "POST",
    body: JSON.stringify({ bookId, userId: getCurrentUserId(), resetContext }),
  }),
  finishQaLearningTask: (bookId: BookId, learningTaskId: string) => request<{ completed: boolean }>(`/rag/learning-tasks/${encodeURIComponent(learningTaskId)}/finish`, {
    method: "POST",
    body: JSON.stringify({ bookId, userId: getCurrentUserId() }),
  }),
  // 诊断只在 start 这一步认人：后端把 userId 存进工作流状态，
  // 后续 answers / finish / 校准都按 diagnosticId 找回同一个用户，不需要再传。
  startDiagnostic: (bookId: BookId, learningGoal?: string, planDayId?: string, planItemId?: string, taskMode: "diagnostic" | "practice" = "diagnostic") => request<DiagnosticStartResult>("/diagnostics/start", { method: "POST", body: JSON.stringify({ bookId, learningGoal, userId: getCurrentUserId(), learningPlanDayId: planDayId ? Number(planDayId) : undefined, learningPlanItemId: planItemId ? Number(planItemId) : undefined, taskMode }) }),
  completeLearningPlanItem: (itemId: string) => request(`/learning-plans/weekly/items/${itemId}/complete`, { method: "POST", body: JSON.stringify({ userId: getCurrentUserId() }) }),
  startLearningPlanItem: (itemId: string) => request(`/learning-plans/weekly/items/${itemId}/start`, { method: "POST", body: JSON.stringify({ userId: getCurrentUserId() }) }),
  executeCode: (code: string, tests: string[]) => request<{ passed: boolean; stdout: string; stderr: string; timed_out: boolean }>("/learning-plans/code/execute", { method: "POST", body: JSON.stringify({ code, tests }) }),
  getCodeTaskContent: (itemId: string) => request<{ kind: string; prompt?: string; starter_code?: string; tests?: string[]; message?: string }>(`/learning-plans/weekly/items/${encodeURIComponent(itemId)}/content`),
  submitDiagnosticAnswer: (diagnosticId: string, payload: { questionId: string; answer: string; skipped?: boolean }) => request(`/diagnostics/${diagnosticId}/answers`, { method: "POST", body: JSON.stringify(payload) }),
  finishDiagnostic: (diagnosticId: string) => request<DiagnosticResult>(`/diagnostics/${diagnosticId}/finish`, { method: "POST" }),
  submitCalibration: (payload: { diagnosticId: string; level: string; reason: string }) => request("/learner-calibrations", { method: "POST", body: JSON.stringify(payload) }),
  generatePlan: (payload: { diagnosticId: string; bookId: BookId; goal: string }) => request<LearningPlanResult>("/learning-plans/generate", { method: "POST", body: JSON.stringify({ ...payload, userId: getCurrentUserId() }) }),
  createMaterialPlan: (payload: MaterialLearningPlanPayload) => request<LearningPlanResult>("/learning-plans/material", { method: "POST", body: JSON.stringify({ ...payload, userId: getCurrentUserId() }) }),
  getLearningPlan: (bookId: BookId, diagnosticId?: string) => {
    const query = new URLSearchParams({ bookId, userId: getCurrentUserId() });
    if (diagnosticId) query.set("diagnosticId", diagnosticId);
    return request<LearningPlanLookup>(`/learning-plans?${query.toString()}`);
  },
  getTodayLearning: (bookId: BookId) => request<TodayLearningResponse>(`/today-learning?userId=${encodeURIComponent(getCurrentUserId())}&bookId=${encodeURIComponent(bookId)}`),
  writeLearningEvent: (payload: { taskId: string; taskTitle: string; eventType: string; status: string; durationSeconds?: number; plannedMinutes?: number }) => request("/learning-events", { method: "POST", body: JSON.stringify({ ...payload, userId: getCurrentUserId() }) }),
  getLearningRecords: (params?: { category?: string; page?: number; pageSize?: number }) => {
  generateWeeklyPlan: async (bookId: BookId, reason = "", aimLevel?: number): Promise<LearningPlanResult> => {
    const response = await request<WeeklyPlanPayload>("/learning-plans/weekly/generate", { method: "POST", body: JSON.stringify({ userId: Number(getCurrentUserId()), bookId: databaseBookId[bookId], reason, ...(aimLevel === undefined ? {} : { aimLevel }) }) });
    return asLearningPlan(response, bookId);
  },
  createMaterialPlan: (payload: MaterialLearningPlanPayload) => request<LearningPlanResult>("/learning-plans/material", { method: "POST", body: JSON.stringify({ ...payload, userId: getCurrentUserId() }) }),
  getLearningPlan: async (bookId: BookId) => {
    const query = new URLSearchParams({ bookId: String(databaseBookId[bookId]), userId: String(Number(getCurrentUserId())) });
    const response = await request<{ exists: boolean; plan: WeeklyPlanPayload | null }>(`/learning-plans/weekly?${query.toString()}`);
    return { exists: response.exists, plan: response.plan ? asLearningPlan(response.plan, bookId) : null };
  },
  getReadingMaterials: async (bookId: BookId, itemTitle: string) => {
    const query = new URLSearchParams({ bookId: String(databaseBookId[bookId]), itemTitle });
    return request<ReadingMaterialResult>(`/learning-plans/weekly/materials?${query.toString()}`);
  },
  getTodayLearning: (bookId: BookId) => request<TodayLearningResponse>(`/today-learning?userId=${encodeURIComponent(getCurrentUserId())}&bookId=${encodeURIComponent(bookId)}`),
  writeLearningEvent: (payload: { taskId: string; taskTitle: string; eventType: string; status: string; bookId?: BookId; durationSeconds?: number; plannedMinutes?: number }) => request("/learning-events", { method: "POST", body: JSON.stringify({ ...payload, userId: getCurrentUserId() }) }),
  getLearningRecords: (params?: { category?: string; startDate?: string; endDate?: string; page?: number; pageSize?: number }) => {
    const query = new URLSearchParams({ userId: getCurrentUserId(), page: String(params?.page ?? 1), pageSize: String(params?.pageSize ?? 50) });
    if (params?.category && params.category !== "all") query.set("category", params.category);
    if (params?.startDate) query.set("startDate", params.startDate);
    if (params?.endDate) query.set("endDate", params.endDate);
    return request<LearningActivityList>(`/learning-records?${query.toString()}`);
  },
  // 有图片时使用 multipart 接口；纯文字问题继续沿用 JSON 接口。
  askQuestion: (payload: QaQuestionPayload) => {
    const conversationId = encodeURIComponent(payload.conversationId ?? "");
    if (payload.attachment) {
      const form = new FormData();
      form.set("userId", getCurrentUserId());
      form.set("bookId", payload.bookId);
      form.set("question", payload.question);
      form.set("allowGeneralFallback", String(payload.allowGeneralFallback ?? false));
      form.set("answerMode", payload.answerMode ?? "direct");
      if (payload.learningTaskId) form.set("learningTaskId", payload.learningTaskId);
      form.set("file", payload.attachment);
      return request<QaResult>(`/rag/conversations/${conversationId}/messages-with-attachment`, { method: "POST", body: form });
    }
    return request<QaResult>(`/rag/conversations/${conversationId}/messages`, { method: "POST", body: JSON.stringify({ bookId: payload.bookId, question: payload.question, userId: getCurrentUserId(), allowGeneralFallback: payload.allowGeneralFallback ?? false, answerMode: payload.answerMode ?? "direct", learningTaskId: payload.learningTaskId ?? null }) });
  },
  // 回读数据库中该用户消息绑定的附件，供消息气泡使用OSS公共URL展示。
  listQaAttachments: (messageId: number) => request<QaAttachment[]>(`/rag/messages/${messageId}/attachments?userId=${encodeURIComponent(getCurrentUserId())}`),
  getLearnerProfile: (userId: string, learningDomain: string) => request<LearnerProfileResult>(`/learner-profile?user_id=${encodeURIComponent(userId)}&learning_domain=${encodeURIComponent(learningDomain)}`),
  askQuestion: (payload: QaQuestionPayload) => request<QaResult>(`/rag/conversations/${encodeURIComponent(payload.conversationId ?? "")}/messages`, { method: "POST", body: JSON.stringify({ bookId: payload.bookId, question: payload.question, userId: getCurrentUserId(), allowGeneralFallback: payload.allowGeneralFallback ?? false, answerMode: payload.answerMode ?? "direct", learningTaskId: payload.learningTaskId ?? null }) }),
  getLearnerProfile: async (userId: string, learningDomain: string): Promise<LearnerProfileResult> => {
    const book = profileBookFor(learningDomain);
    const query = new URLSearchParams({ user_id: userId, book_id: String(book.databaseBookId) });
    const response = await request<MySqlProfileSetup>(`/learner-profile/setup?${query.toString()}`);
    return asLearnerProfile(response, userId, learningDomain);
  },
  getKnowledgePoints: (learningDomain: string) => request<KnowledgePointResult>(`/learner-profile/knowledge-points?learning_domain=${encodeURIComponent(learningDomain)}`),
  saveLearnerProfile: async (payload: LearnerProfilePayload) => {
    const book = profileBookFor(payload.learning_domain);
    const goalResult = await realApi.getLearnerGoal(book.uiBookId);
    if (!goalResult.exists || !goalResult.goal) {
      throw { code: "LEARNING_GOAL_REQUIRED", message: "请先在“选书与目标”中保存目标，再保存学习画像。", retryable: false } satisfies ApiError;
    }
    const goal = goalResult.goal;
    const setup = await request<MySqlProfileSetup>("/learner-profile/setup", {
      method: "POST",
      body: JSON.stringify({
        user_id: Number(payload.user_id),
        book_id: book.databaseBookId,
        background: payload.background,
        preferred_content_style: payload.preferences.content_style,
        preferred_difficulty: payload.preferences.difficulty,
        learning_frequency: payload.preferences.learning_frequency,
        self_assessed_level: payload.self_assessed_level,
        current_confusions: payload.current_confusions,
        additional_requirements: payload.additional_requirements,
        preferred_activity_types: payload.preferences.activity_types,
        session_duration_minutes: payload.preferences.session_duration_minutes,
        goal: goal.targetLevel,
        aim_level: aimLevelByTarget[goal.targetLevel] ?? 1,
        daily_minutes: goal.dailyMinutes,
        start_date: new Date().toISOString().slice(0, 10),
        target_date: goal.targetDate ?? null,
      }),
    });
    return asLearnerProfile(setup, payload.user_id, payload.learning_domain);
  },
};

export const api = USE_REAL_API ? realApi : mockApi;

export type PracticeQuestion = { id: number; content: string; type: string; options: Array<{ key?: string; id?: string; text?: string; label?: string }> };
export type PracticeStats = { answerCount: number; correctCount: number; accuracy: number; studySeconds?: number };
export type PracticeAnswerResult = { correct: boolean; correctAnswer: string; explanation: string; statistics: PracticeStats };
export type PracticeLeader = { rank: number; userId: number; name: string; answers: number; correct: number; accuracy: number; studySeconds: number; taskCount: number; streakBonus: number; score: number };
export type PracticeAchievement = { id: number; code: string; title: string; detail: string; icon: string; tone: string; current: number; target: number; progress: number; earned: boolean; earnedAt: string | null; statusText: string };
export type PracticeAchievements = { earnedCount: number; totalCount: number; items: PracticeAchievement[]; newlyUnlocked: PracticeAchievement[] };
export const practiceApi = {
  start: (bookId: string) => request<{ sessionId: number; question: PracticeQuestion | null }>("/practice/sessions", { method: "POST", body: JSON.stringify({ userId: Number(getCurrentUserId()), bookId }) }),
  next: (sessionId: number) => request<{ question: PracticeQuestion | null }>(`/practice/sessions/${sessionId}/next?userId=${encodeURIComponent(getCurrentUserId())}`),
  answer: (sessionId: number, questionId: number, answer: string) => request<PracticeAnswerResult>(`/practice/sessions/${sessionId}/answers`, { method: "POST", body: JSON.stringify({ userId: Number(getCurrentUserId()), questionId, answer }) }),
  finish: (sessionId: number) => request<PracticeStats>(`/practice/sessions/${sessionId}/finish?userId=${encodeURIComponent(getCurrentUserId())}`, { method: "POST" }),
  leaderboard: (period: "week" | "month") => request<{ items: PracticeLeader[] }>(`/practice/leaderboard?period=${period}`),
  overview: (period: "week" | "month" = "week") => request<PracticeStats>(`/practice/overview?userId=${encodeURIComponent(getCurrentUserId())}&period=${period}`),
  achievements: () => request<PracticeAchievements>(`/practice/achievements?userId=${encodeURIComponent(getCurrentUserId())}`),
  achievementProgress: (force = false) => request<PracticeAchievements>(`/practice/achievements/progress?userId=${encodeURIComponent(getCurrentUserId())}&force=${force}`),
  acknowledgeAchievement: (achievementId: number) => request<{ acknowledged: boolean; achievementId: number }>(`/practice/achievements/${achievementId}/acknowledge`, { method: "POST", body: JSON.stringify({ userId: Number(getCurrentUserId()) }) }),
};

export type ApiTaskPayload = LearningTask;
