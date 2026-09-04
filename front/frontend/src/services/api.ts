import { books, getBookContent, type BookId, type DiagnosticQuestion, type LearningTask, type Source } from "../data/mockData";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
// Use the backend by default. Set VITE_USE_REAL_API=false only for an explicit
// standalone Mock demonstration.
export const USE_REAL_API = import.meta.env.VITE_USE_REAL_API !== "false";

export type ApiState = "initial" | "loading" | "ready" | "empty" | "submitting" | "success" | "error" | "offline" | "stale";
export type ApiError = { code: string; message: string; requestId?: string; retryable?: boolean; details?: unknown };
export type BookCatalogItem = { id: string; title: string; shortTitle: string; subtitle: string; knowledgePointCount?: number; available?: boolean };
export type BookCatalog = { books: BookCatalogItem[] };
export type LearnerGoalPayload = { bookId: string; targetLevel: string; weeklyHours: number };
export type LearnerGoalResult = LearnerGoalPayload & { goalId: string; updatedAt?: string; rescheduled?: boolean; estimatedDays?: number | null; planRefreshSuggested?: boolean };
export type LearnerGoalLookup = { exists: boolean; goal?: LearnerGoalResult };
export type LearningResource = { title: string; platform: string; url: string; language: string; kind: string; note: string };
export type KnowledgePointResources = { knowledgePointId: string; resources: LearningResource[] };
export type ResourceCatalog = { items: KnowledgePointResources[] };

export type DiagnosticStartResult = { diagnosticId: string; questions: DiagnosticQuestion[] };
export type DiagnosticResult = { level: string; accuracy: string; confidence: string; evidence: string; answerPerformance: string; generatedAt: string; relatedScope: string };
export type LearningPlanBook = { id: string; title: string; shortTitle: string };
export type LearningPlanResult = { book: LearningPlanBook; goal: string; goalLevel: string; tasks: LearningTask[]; advice: string[]; resources: Source[] };
export type LearningPlanLookup = { exists: boolean; plan: LearningPlanResult | null };
/** MySQL 中 learning_plan / learning_plan_day / learning_plan_day_item 的七天计划读取结构。 */
export type WeeklyPlanItem = {
  id: number;
  title: string;
  description: string;
  status: "todo" | "in_progress" | "completed" | "skipped" | string;
  source: string;
  adaptive_reason: string;
  item_type: string;
};
export type WeeklyPlanDay = {
  id: number;
  title: string;
  adaptive_reason: string;
  expected_date: string;
  generated_version: number;
  priority_score: number;
  items: WeeklyPlanItem[];
};
export type WeeklyPlan = {
  plan: { id: number; goal_id: number; window_start_date: string; window_end_date: string; daily_minutes: number; adaptive_version: number };
  days: WeeklyPlanDay[];
};
export type WeeklyPlanLookup = { exists: boolean; plan: WeeklyPlan | null };
export type ReadingMaterials = {
  item_title: string;
  knowledge_point: { id: number; name: string; code: string };
  integrated_content: string;
  generated_by: "llm" | "textbook_fallback" | "blocked" | string;
  references: Array<{ title: string; location: string }>;
  search_error: string | null;
};
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
export type QaQuestionPayload = { bookId: BookId; question: string; conversationId?: string; sources?: Source[] };
export type QaResult = { answer: string; refused: boolean; citations: Source[]; relatedKnowledgePoints?: string[]; recommendedAction?: string; conversationId?: string; requestId?: string };
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
export type ProfileSetupPayload = { user_id: number; book_id: number; background: string; preferred_content_style: string; goal: string; aim_level: number; daily_minutes: number; start_date?: string | null; target_date?: string | null };
export type ProfileMastery = { knowledge_point_id: number; name: string; mastery_score: number; aim_score: number; gap_score: number; confidence: number; next_review_at?: string | null };
export type ProfileSetup = { user_id: number; book_id: number; background: string; preferred_content_style: string; goal: { id: number; goal: string; aim_level: number; daily_minutes: number; start_date?: string | null; target_date?: string | null; status: number } | null; mastery: ProfileMastery[] };
export type ProfileSetupResult = { exists: boolean; profile: ProfileSetup | null };

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
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
const mockGoals = new Map<string, LearnerGoalResult>();

/**
 * 页面演示使用的模拟服务。它与真实接口保持同一组动作名称，后端接入时只替换服务实现。
 */
export const mockApi = {
  async getBooks(): Promise<BookCatalog> {
    await wait(120);
    return { books: books.map((book) => ({ id: book.id, title: book.title, shortTitle: book.shortTitle, subtitle: book.subtitle, available: true })) };
  },
  async getLearningResources(knowledgePointIds?: string[]): Promise<ResourceCatalog> {
    await wait(120);
    return { items: (knowledgePointIds ?? []).map((knowledgePointId) => ({ knowledgePointId, resources: [] })) };
  },
  async saveLearnerGoal(payload: LearnerGoalPayload): Promise<LearnerGoalResult> {
    await wait(160);
    const goal = { ...payload, goalId: `goal-${payload.bookId}`, updatedAt: new Date().toISOString() };
    mockGoals.set(payload.bookId, goal);
    return goal;
  },
  async getLearnerGoal(bookId: string): Promise<LearnerGoalLookup> {
    await wait(100);
    const goal = mockGoals.get(bookId);
    return goal ? { exists: true, goal } : { exists: false };
  },
  async createConversation(bookId: BookId): Promise<QaConversation> {
    await wait(260);
    return { conversationId: `mock-qa-${Date.now()}`, bookId, userId: "user_001", createdAt: new Date().toISOString(), status: "active" };
  },
  async startDiagnostic(bookId: BookId, _learningGoal?: string, _userId?: number, _learningPlanDayId?: number, _learningPlanItemId?: number): Promise<DiagnosticStartResult> {
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
      weeklyProgress: { progressPercent: 0, completedTaskCount: 0, totalTaskCount: content.todayTasks.length, studyDurationSeconds: 0, studyDurationHours: 0, accuracy: 0, dailyDuration: [] },
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
  async writeLearningEvent(payload: { taskId: string; taskTitle: string; eventType: string; status: string; userId?: string; bookId?: string; detail?: Record<string, unknown> }) {
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
    return { answer: "这是一个很好的追问。建议先从定义、输入条件和输出结果三个角度拆解，再结合引用资料核对关键概念。", refused: false, citations: payload.sources };
  },
  async getWeeklyLearningPlan(_userId: number, _bookId: number): Promise<WeeklyPlanLookup> {
    await wait(180);
    const start = new Date();
    const days: WeeklyPlanDay[] = Array.from({ length: 7 }, (_, index) => {
      const current = new Date(start); current.setDate(start.getDate() + index);
      return {
        id: index + 1, title: `第 ${index + 1} 天学习计划`, expected_date: current.toISOString().slice(0, 10), generated_version: 1, priority_score: 1, adaptive_reason: "根据当前掌握度与目标掌握度生成。",
        items: [
          { id: index * 10 + 1, title: "学习前诊断（10分钟）", description: "先完成诊断题，校准今天后续阅读内容。", status: "todo", source: "review_due", adaptive_reason: "每日先诊断，再安排后续学习。", item_type: "text_learning" },
          { id: index * 10 + 2, title: "阅读：对应教材章节（15分钟）", description: "阅读教材中的核心概念，整理定义、例子和疑问。", status: "todo", source: "weak_point", adaptive_reason: "当前掌握度尚未达到目标掌握度。", item_type: "text_learning" },
        ],
      };
    });
    return { exists: true, plan: { plan: { id: 1, goal_id: 1, window_start_date: days[0].expected_date, window_end_date: days[6].expected_date, daily_minutes: 30, adaptive_version: 1 }, days } };
  },
  async generateWeeklyLearningPlan(userId: number, bookId: number): Promise<WeeklyPlan> {
    await wait(360);
    const result = await this.getWeeklyLearningPlan(userId, bookId);
    if (!result.plan) throw { code: "PLAN_GENERATION_FAILED", message: "未能生成七天计划" } satisfies ApiError;
    return result.plan;
  },
  async getReadingMaterials(bookId: number, _itemTitle: string): Promise<ReadingMaterials> {
    await wait(280);
    const name = bookId === 2 ? "机器学习知识点" : "人工智能知识点";
    return { item_title: _itemTitle, knowledge_point: { id: 0, name, code: "mock" }, integrated_content: "这是基于本地教材生成的统一学习讲义。真实模式会将对应知识点的教材正文作为权威依据，并仅将网络资料作为补充。", generated_by: "textbook_fallback", references: [], search_error: "模拟模式不执行网络检索。" };
  },
  async completeWeeklyPlanItem(itemId: number, _userId: number) {
    await wait(220);
    return { item_id: itemId, status: "completed" };
  },
  async getProfileSetup(_userId: number, _bookId: number): Promise<ProfileSetupResult> { await wait(260); return { exists: false, profile: null }; },
  async saveProfileSetup(payload: ProfileSetupPayload): Promise<ProfileSetupResult> { await wait(420); return { exists: true, profile: { user_id: payload.user_id, book_id: payload.book_id, background: payload.background, preferred_content_style: payload.preferred_content_style, goal: { id: 0, goal: payload.goal, aim_level: payload.aim_level, daily_minutes: payload.daily_minutes, start_date: payload.start_date ?? null, target_date: payload.target_date ?? null, status: 0 }, mastery: [] } }; },
};

/**
 * 真实服务的接口映射。启用 VITE_USE_REAL_API=true 后，页面可以切换到后端。
 */
export const realApi = {
  getBooks: async (): Promise<BookCatalog> => {
    try { return await request<BookCatalog>("/books"); } catch { return mockApi.getBooks(); }
  },
  getLearningResources: async (knowledgePointIds?: string[]): Promise<ResourceCatalog> => {
    const query = knowledgePointIds?.length ? `?knowledgePointIds=${encodeURIComponent(knowledgePointIds.join(","))}` : "";
    try { return await request<ResourceCatalog>(`/learning-resources${query}`); } catch { return mockApi.getLearningResources(knowledgePointIds); }
  },
  saveLearnerGoal: async (payload: LearnerGoalPayload): Promise<LearnerGoalResult> => {
    try { return await request<LearnerGoalResult>("/learner-goals", { method: "POST", body: JSON.stringify(payload) }); } catch { return mockApi.saveLearnerGoal(payload); }
  },
  getLearnerGoal: async (bookId: string): Promise<LearnerGoalLookup> => {
    try { return await request<LearnerGoalLookup>(`/learner-goals?bookId=${encodeURIComponent(bookId)}`); } catch { return mockApi.getLearnerGoal(bookId); }
  },
  createConversation: (bookId: BookId) => request<QaConversation>("/rag/conversations", { method: "POST", body: JSON.stringify({ bookId, userId: "user_001" }) }),
  startDiagnostic: (bookId: BookId, learningGoal?: string, userId?: number, learningPlanDayId?: number, learningPlanItemId?: number) => request<DiagnosticStartResult>("/diagnostics/start", { method: "POST", body: JSON.stringify({ bookId, learningGoal, userId: userId ? String(userId) : undefined, learningPlanDayId, learningPlanItemId }) }),
  submitDiagnosticAnswer: (diagnosticId: string, payload: { questionId: string; answer: string; skipped?: boolean }) => request(`/diagnostics/${diagnosticId}/answers`, { method: "POST", body: JSON.stringify(payload) }),
  finishDiagnostic: (diagnosticId: string) => request<DiagnosticResult>(`/diagnostics/${diagnosticId}/finish`, { method: "POST" }),
  submitCalibration: (payload: { diagnosticId: string; level: string; reason: string }) => request("/learner-calibrations", { method: "POST", body: JSON.stringify(payload) }),
  generatePlan: (payload: { diagnosticId: string; bookId: BookId; goal: string }) => request<LearningPlanResult>("/learning-plans/generate", { method: "POST", body: JSON.stringify(payload) }),
  createMaterialPlan: (payload: MaterialLearningPlanPayload) => request<LearningPlanResult>("/learning-plans/material", { method: "POST", body: JSON.stringify(payload) }),
  getLearningPlan: (bookId: BookId, diagnosticId?: string) => {
    const query = new URLSearchParams({ bookId });
    if (diagnosticId) query.set("diagnosticId", diagnosticId);
    return request<LearningPlanLookup>(`/learning-plans?${query.toString()}`);
  },
  getTodayLearning: (bookId: BookId) => request<TodayLearningResponse>(`/today-learning?userId=user_001&bookId=${encodeURIComponent(bookId)}`),
  writeLearningEvent: (payload: { taskId: string; taskTitle: string; eventType: string; status: string; userId?: string; bookId?: string; detail?: Record<string, unknown> }) => request("/learning-events", { method: "POST", body: JSON.stringify({ ...payload, userId: payload.userId ?? "user_001" }) }),
  getLearningRecords: (params?: { category?: string; page?: number; pageSize?: number }) => {
    const query = new URLSearchParams({ userId: "user_001", page: String(params?.page ?? 1), pageSize: String(params?.pageSize ?? 50) });
    if (params?.category && params.category !== "all") query.set("category", params.category);
    return request<LearningActivityList>(`/learning-records?${query.toString()}`);
  },
  askQuestion: (payload: QaQuestionPayload) => request<QaResult>(`/rag/conversations/${encodeURIComponent(payload.conversationId ?? "")}/messages`, { method: "POST", body: JSON.stringify({ bookId: payload.bookId, question: payload.question, userId: "user_001" }) }),
  getWeeklyLearningPlan: (userId: number, bookId: number) => request<WeeklyPlanLookup>(`/learning-plans/weekly?${new URLSearchParams({ userId: String(userId), bookId: String(bookId) })}`),
  generateWeeklyLearningPlan: (userId: number, bookId: number) => request<WeeklyPlan>("/learning-plans/weekly/generate", { method: "POST", body: JSON.stringify({ userId, bookId }) }),
  getReadingMaterials: (bookId: number, itemTitle: string) => request<ReadingMaterials>(`/learning-plans/weekly/materials?${new URLSearchParams({ bookId: String(bookId), itemTitle })}`),
  completeWeeklyPlanItem: (itemId: number, userId: number) => request<{ item_id: number; status: string }>(`/learning-plans/weekly/items/${itemId}/complete`, { method: "POST", body: JSON.stringify({ userId }) }),
  getProfileSetup: (userId: number, bookId: number) => request<ProfileSetupResult>(`/learner-profile/setup?user_id=${userId}&book_id=${bookId}`),
  saveProfileSetup: (payload: ProfileSetupPayload) => request<ProfileSetupResult>("/learner-profile/setup", { method: "POST", body: JSON.stringify(payload) }),
};

export const api = USE_REAL_API ? realApi : mockApi;

export type ApiTaskPayload = LearningTask;
