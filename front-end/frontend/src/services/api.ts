import type { BookId, DiagnosticQuestion, LearningTask, Source } from "../data/mockData";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
export const USE_REAL_API = import.meta.env.VITE_USE_REAL_API === "true";

export type ApiState = "initial" | "loading" | "ready" | "empty" | "submitting" | "success" | "error" | "offline" | "stale";
export type ApiError = { code: string; message: string; requestId?: string; retryable?: boolean; details?: unknown };

export type DiagnosticStartResult = { diagnosticId: string; questions: DiagnosticQuestion[] };
export type DiagnosticResult = { diagnosticId?: string; level: string; accuracy: string; confidence: string; evidence: string; suggestions: string[] };
export type QaResult = { answer: string; citations: Source[] };

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

/**
 * 页面演示使用的模拟服务。它与真实接口保持同一组动作名称，后端接入时只替换服务实现。
 */
export const mockApi = {
  async startDiagnostic(bookId: BookId): Promise<DiagnosticStartResult> {
    await wait();
    return { diagnosticId: `demo-${bookId}-diagnostic`, questions: [] };
  },
  async submitDiagnosticAnswer(diagnosticId: string, payload: { questionId: string; answer: string; skipped?: boolean }) {
    await wait(260);
    return { diagnosticId, ...payload, saved: true };
  },
  async finishDiagnostic(diagnosticId: string): Promise<DiagnosticResult> {
    await wait(520);
    return { diagnosticId, level: "中等偏上", accuracy: "75%", confidence: "高", evidence: "最近 3 道题的作答结果以及关联知识点表现。", suggestions: ["先补齐当前薄弱知识点", "完成短练习后进行一次复测"] };
  },
  async submitCalibration(payload: { diagnosticId: string; level: string; reason: string }) {
    await wait(420);
    return { calibrationId: `calibration-${Date.now()}`, ...payload, saved: true };
  },
  async generatePlan(payload: { bookId: BookId; goal: string }) {
    await wait(520);
    return { planId: `plan-${payload.bookId}`, goal: payload.goal, generated: true };
  },
  async writeLearningEvent(payload: { taskId: string; eventType: string; status: string }) {
    await wait(260);
    return { eventId: `event-${Date.now()}`, ...payload, saved: true };
  },
  async askQuestion(payload: { bookId: BookId; question: string; sources: Source[] }): Promise<QaResult> {
    await wait(720);
    if (payload.question.includes("接口失败")) throw { code: "QA_TEMPORARY_ERROR", message: "资料问答暂时不可用，请稍后重试。", retryable: true } satisfies ApiError;
    return { answer: "这是一个很好的追问。建议先从定义、输入条件和输出结果三个角度拆解，再结合引用资料核对关键概念。", citations: payload.sources };
  },
};

/**
 * 真实服务的接口映射。启用 VITE_USE_REAL_API=true 后，页面可以切换到后端。
 */
export const realApi = {
  startDiagnostic: (bookId: BookId) => request<DiagnosticStartResult>("/diagnostics/start", { method: "POST", body: JSON.stringify({ bookId }) }),
  submitDiagnosticAnswer: (diagnosticId: string, payload: { questionId: string; answer: string; skipped?: boolean }) => request(`/diagnostics/${diagnosticId}/answers`, { method: "POST", body: JSON.stringify(payload) }),
  finishDiagnostic: (diagnosticId: string) => request<DiagnosticResult>(`/diagnostics/${diagnosticId}/finish`, { method: "POST" }),
  submitCalibration: (payload: { diagnosticId: string; level: string; reason: string }) => request("/learner-calibrations", { method: "POST", body: JSON.stringify(payload) }),
  generatePlan: (payload: { bookId: BookId; goal: string }) => request("/learning-plans/generate", { method: "POST", body: JSON.stringify(payload) }),
  writeLearningEvent: (payload: { taskId: string; eventType: string; status: string }) => request("/learning-events", { method: "POST", body: JSON.stringify(payload) }),
  askQuestion: (payload: { bookId: BookId; question: string }) => request<QaResult>("/rag/ask", { method: "POST", body: JSON.stringify(payload) }),
};

export const api = USE_REAL_API ? realApi : mockApi;

export type ApiTaskPayload = LearningTask;
