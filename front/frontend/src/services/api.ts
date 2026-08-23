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
export type LearnerGoalPayload = { bookId: string; targetLevel: string; weeklyHours: number };
export type LearnerGoalResult = {
  goalId: string; bookId: string; targetLevel: string; weeklyHours: number; updatedAt?: string;
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
 * 排课时间预算。由后端按「每周时长 ÷ 7」得到每日分钟数，
 * 再用历史「计划 vs 实际」的中位数比值（paceFactor）折算实际占用。
 * 任务自己的 minutes 始终是 AI 的原始估计，不会被校准值改写。
 */
export type PlanTimeBudget = { dailyMinutes: number; totalMinutes: number; estimatedDays: number; paceFactor: number; adjustedTotalMinutes: number };
export type LearningPlanResult = { book: LearningPlanBook; goal: string; goalLevel: string; tasks: LearningTask[]; advice: string[]; resources: Source[]; timeBudget?: PlanTimeBudget };
export type LearningPlanLookup = { exists: boolean; plan: LearningPlanResult | null };
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
export type QaConversation = { conversationId: string; bookId: BookId; userId: string; createdAt: string; status: string };
/**
 * allowGeneralFallback：资料检索不足以回答时，是否允许改用通用模型作答。
 * 默认 false —— 必须由用户在界面上显式确认后才置为 true，避免无出处的答案被当成教材依据。
 * 【后端接入清单】POST /rag/conversations/{id}/messages 需接收该字段，
 * 并在降级作答时返回 answeredByGeneralModel=true、citations=[]。
 */
export type QaQuestionPayload = { bookId: BookId; question: string; conversationId?: string; sources?: Source[]; allowGeneralFallback?: boolean };
export type QaResult = { answer: string; refused: boolean; citations: Source[]; relatedKnowledgePoints?: string[]; recommendedAction?: string; conversationId?: string; requestId?: string; /** 后端确认本次回答来自通用模型（无教材出处） */ answeredByGeneralModel?: boolean };
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
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json", ...getAuthHeaders(), ...init?.headers },
      ...init,
    });
    if (!response.ok) {
      const error = (await response.json().catch(() => null)) as ApiError | null;
      throw error ?? { code: `HTTP_${response.status}`, message: "请求失败", retryable: response.status >= 500 };
    }
    return response.status === 204 ? (undefined as T) : (await response.json()) as T;
  } catch (error) {
    if (error && typeof error === "object" && "code" in error) throw error;
    throw { code: "NETWORK_ERROR", message: "网络暂时不可用，请稍后重试。", retryable: true } satisfies ApiError;
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
  async createConversation(bookId: BookId): Promise<QaConversation> {
    await wait(260);
    return { conversationId: `mock-qa-${Date.now()}`, bookId, userId: getCurrentUserId(), createdAt: new Date().toISOString(), status: "active" };
  },
  async startDiagnostic(bookId: BookId): Promise<DiagnosticStartResult> {
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
    await wait(260);
    return { eventId: `event-${Date.now()}`, ...payload, saved: true };
  },
  async getLearningRecords(_params?: { category?: string; page?: number; pageSize?: number }): Promise<LearningActivityList> {
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
    return { answer: "这是一个很好的追问。建议先从定义、输入条件和输出结果三个角度拆解，再结合引用资料核对关键概念。", refused: false, citations: payload.sources };
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
  createConversation: (bookId: BookId) => request<QaConversation>("/rag/conversations", { method: "POST", body: JSON.stringify({ bookId, userId: getCurrentUserId() }) }),
  // 诊断只在 start 这一步认人：后端把 userId 存进工作流状态，
  // 后续 answers / finish / 校准都按 diagnosticId 找回同一个用户，不需要再传。
  startDiagnostic: (bookId: BookId, learningGoal?: string) => request<DiagnosticStartResult>("/diagnostics/start", { method: "POST", body: JSON.stringify({ bookId, learningGoal, userId: getCurrentUserId() }) }),
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
    const query = new URLSearchParams({ userId: getCurrentUserId(), page: String(params?.page ?? 1), pageSize: String(params?.pageSize ?? 50) });
    if (params?.category && params.category !== "all") query.set("category", params.category);
    return request<LearningActivityList>(`/learning-records?${query.toString()}`);
  },
  askQuestion: (payload: QaQuestionPayload) => request<QaResult>(`/rag/conversations/${encodeURIComponent(payload.conversationId ?? "")}/messages`, { method: "POST", body: JSON.stringify({ bookId: payload.bookId, question: payload.question, userId: getCurrentUserId(), allowGeneralFallback: payload.allowGeneralFallback ?? false }) }),
  getLearnerProfile: (userId: string, learningDomain: string) => request<LearnerProfileResult>(`/learner-profile?user_id=${encodeURIComponent(userId)}&learning_domain=${encodeURIComponent(learningDomain)}`),
  getKnowledgePoints: (learningDomain: string) => request<KnowledgePointResult>(`/learner-profile/knowledge-points?learning_domain=${encodeURIComponent(learningDomain)}`),
  saveLearnerProfile: async (payload: LearnerProfilePayload) => {
    const started = await request<LearnerProfileWorkflowStart>("/learner-profile/workflows", { method: "POST", body: JSON.stringify(payload) });
    return request<LearnerProfileResult>(`/learner-profile/workflows/${encodeURIComponent(started.workflowId)}/review`, { method: "POST", body: JSON.stringify({ action: "approve" }) });
  },
};

export const api = USE_REAL_API ? realApi : mockApi;

export type ApiTaskPayload = LearningTask;
