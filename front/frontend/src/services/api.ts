import { books, getBookContent, type BookId, type DiagnosticQuestion, type LearningTask, type Source } from "../data/mockData";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
// Use the backend by default. Set VITE_USE_REAL_API=false only for an explicit
// standalone Mock demonstration.
export const USE_REAL_API = import.meta.env.VITE_USE_REAL_API !== "false";
const USER_STORAGE_KEY = "study-companion-user-id";
const TOKEN_STORAGE_KEY = "study-companion-access-token";

export function currentAccessToken(): string {
  const configured = String(import.meta.env.VITE_AUTH_TOKEN ?? "").trim();
  if (configured) return configured;
  if (typeof window !== "undefined") {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY)?.trim() ?? "";
  }
  return "";
}

function tokenSubject(token: string): string {
  try {
    const encoded = token.split(".")[1] ?? "";
    const normalized = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const payload = JSON.parse(window.atob(padded)) as { sub?: unknown };
    return typeof payload.sub === "string" ? payload.sub.trim() : "";
  } catch {
    return "";
  }
}

export function currentUserId(): string {
  const accessToken = currentAccessToken();
  if (accessToken && typeof window !== "undefined") {
    const verifiedByBackend = tokenSubject(accessToken);
    if (verifiedByBackend) return verifiedByBackend;
  }
  const configured = String(import.meta.env.VITE_USER_ID ?? "").trim();
  if (configured) return configured;
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(USER_STORAGE_KEY)?.trim();
    if (stored) return stored;
  }
  return "user_001";
}

export type ApiState = "initial" | "loading" | "ready" | "empty" | "submitting" | "success" | "error" | "offline" | "stale";
export type ApiError = { code: string; message: string; requestId?: string; retryable?: boolean; details?: unknown };

export type DiagnosticStartResult = { diagnosticId: string; questions: DiagnosticQuestion[] };
export type DiagnosticResult = { level: string; accuracy: string; confidence: string; evidence: string; answerPerformance: string; generatedAt: string; relatedScope: string };
export type LearningPlanBook = { id: string; title: string; shortTitle: string };
export type LearningPlanResult = { book: LearningPlanBook; goal: string; goalLevel: string; tasks: LearningTask[]; advice: string[]; resources: Source[] };
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
export type QaQuestionPayload = { bookId: BookId; question: string; conversationId?: string; requestId?: string; sources?: Source[] };
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
    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    const accessToken = currentAccessToken();
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    else headers.set("X-User-Id", currentUserId());
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
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
const newRequestId = () => typeof crypto !== "undefined" && "randomUUID" in crypto ? `qa-${crypto.randomUUID()}` : `qa-${Date.now()}-${Math.random().toString(16).slice(2)}`;

/**
 * 页面演示使用的模拟服务。它与真实接口保持同一组动作名称，后端接入时只替换服务实现。
 */
export const mockApi = {
  async createConversation(bookId: BookId): Promise<QaConversation> {
    await wait(260);
    return { conversationId: `mock-qa-${Date.now()}`, bookId, userId: currentUserId(), createdAt: new Date().toISOString(), status: "active" };
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
  async writeLearningEvent(payload: { taskId: string; eventType: string; status: string }) {
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
  createConversation: (bookId: BookId) => request<QaConversation>("/rag/conversations", { method: "POST", body: JSON.stringify({ bookId, userId: currentUserId() }) }),
  startDiagnostic: (bookId: BookId, learningGoal?: string) => request<DiagnosticStartResult>("/diagnostics/start", { method: "POST", body: JSON.stringify({ bookId, learningGoal }) }),
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
  getTodayLearning: (bookId: BookId) => request<TodayLearningResponse>(`/today-learning?userId=${encodeURIComponent(currentUserId())}&bookId=${encodeURIComponent(bookId)}`),
  writeLearningEvent: (payload: { taskId: string; taskTitle: string; eventType: string; status: string }) => request("/learning-events", { method: "POST", body: JSON.stringify({ ...payload, userId: currentUserId() }) }),
  getLearningRecords: (params?: { category?: string; page?: number; pageSize?: number }) => {
    const query = new URLSearchParams({ userId: currentUserId(), page: String(params?.page ?? 1), pageSize: String(params?.pageSize ?? 50) });
    if (params?.category && params.category !== "all") query.set("category", params.category);
    return request<LearningActivityList>(`/learning-records?${query.toString()}`);
  },
  askQuestion: (payload: QaQuestionPayload) => request<QaResult>(`/rag/conversations/${encodeURIComponent(payload.conversationId ?? "")}/messages`, { method: "POST", body: JSON.stringify({ bookId: payload.bookId, question: payload.question, userId: currentUserId(), requestId: payload.requestId ?? newRequestId() }) }),
  getLearnerProfile: (userId: string, learningDomain: string) => request<LearnerProfileResult>(`/learner-profile?user_id=${encodeURIComponent(userId)}&learning_domain=${encodeURIComponent(learningDomain)}`),
  getKnowledgePoints: (learningDomain: string) => request<KnowledgePointResult>(`/learner-profile/knowledge-points?learning_domain=${encodeURIComponent(learningDomain)}`),
  saveLearnerProfile: async (payload: LearnerProfilePayload) => {
    const started = await request<LearnerProfileWorkflowStart>("/learner-profile/workflows", { method: "POST", body: JSON.stringify(payload) });
    return request<LearnerProfileResult>(`/learner-profile/workflows/${encodeURIComponent(started.workflowId)}/review`, { method: "POST", body: JSON.stringify({ action: "approve" }) });
  },
};

export const api = USE_REAL_API ? realApi : mockApi;

export type ApiTaskPayload = LearningTask;
