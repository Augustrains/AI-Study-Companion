import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./components/Icon";
import { LearnerProfileView } from "./components/LearnerProfileView";
import { api, type ApiError, type DiagnosticResult, type LearningActivity, type LearningPlanResult, type ReadingMaterials, type TodayLearningResponse, type WeeklyPlan, type WeeklyPlanItem } from "./services/api";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Icon, type IconName } from "./components/Icon";
import { LearnerProfileView } from "./components/LearnerProfileView";
import { AuthView } from "./components/AuthView";
import { GoalsSetupView } from "./components/GoalsSetupView";
import { SettingsView } from "./components/SettingsView";
import { InlineResources, LearningResourcesView } from "./components/LearningResources";
import { HelpCenterView } from "./components/HelpCenter";
import { CommunityView } from "./components/CommunityView";
import { auth, getSession, type AuthUser } from "./services/session";
import { api, type ApiError, type BookCatalogItem, type DiagnosticResult, type LearningActivity, type LearningPlanResult, type PlanTimeBudget, type QaAnswerMode, type TodayLearningResponse } from "./services/api";
import {
  books,
  getBookContent,
  type Book,
  type BookId,
  type DiagnosticQuestion,
  type LearningTask,
  type NavKey,
  type RecordItem,
  type Source,
  type TaskStatus,
} from "./data/mockData";

type Toast = { title: string; message: string } | null;
type Calibration = "lower" | "same" | "higher";
type QaMessage = { role: "user" | "assistant"; text: string; citations?: Source[] };
type QaMessage = {
  role: "user" | "assistant";
  text: string;
  citations?: Source[];
  /** 资料检索不足、后端拒答；此时提供「用通用模型回答」入口 */
  refused?: boolean;
  /** 该回答来自通用模型，没有教材出处，需要显著区分 */
  fromGeneralModel?: boolean;
  /** 触发这条回答的原始问题，用于降级重问 */
  question?: string;
  answerMode?: QaAnswerMode;
  socraticState?: string | null;
  responseQuality?: string | null;
  socraticCompleted?: boolean;
};
type ModalState = {
  title: string;
  subtitle?: string;
  content: ReactNode;
  primary?: { label: string; onClick: () => void; disabled?: boolean };
  secondary?: { label: string; onClick: () => void };
};

const databaseBookIds: Record<BookId, number> = { ml: 2, dl: 1 };
const queryUserId = () => {
  const id = Number(new URLSearchParams(window.location.search).get("user_id"));
  return Number.isInteger(id) && id > 0 ? id : null;
};

const sourceChapterKey = (source: Source) => [
  source.bookId ?? "",
  source.chapterId ?? source.contentUnitId ?? source.location ?? source.title,
].join("::");

const mergeSourcesByChapter = (sources: Source[]) =>
  Array.from(new Map(sources.map((source) => [sourceChapterKey(source), source])).values());

function toRecordItem(activity: LearningActivity): RecordItem {
  const visual = {
    profile: { tone: "violet", icon: "calendar" as const },
    qa: { tone: "amber", icon: "chat" as const },
    diagnostic: { tone: "blue", icon: "target" as const },
    task: { tone: "green", icon: "check" as const },
  }[activity.category];
  const occurredAt = new Date(activity.occurredAt);
  const time = Number.isNaN(occurredAt.getTime()) ? activity.occurredAt : occurredAt.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  return { id: activity.id, title: activity.title, description: activity.description, time, tone: visual.tone, category: activity.category, icon: visual.icon };
}

const navigation: Array<{ key: NavKey; label: string; icon: IconName }> = [
  { key: "today", label: "今日学习", icon: "home" },
  { key: "profile", label: "学习画像", icon: "user" },
  { key: "diagnostic", label: "能力诊断", icon: "target" },
  { key: "plan", label: "学习计划", icon: "calendar" },
  { key: "records", label: "学习记录", icon: "chart" },
  { key: "qa", label: "资料问答", icon: "chat" },
  { key: "resources", label: "学习资源", icon: "spark" },
  { key: "community", label: "学习社区", icon: "users" },
];

const statusLabels: Record<TaskStatus, string> = {
  completed: "已完成",
  in_progress: "进行中",
  todo: "待开始",
  review_due: "待复测",
  skipped: "已跳过",
  rescheduled: "已改期",
};

const errorMessage = (error: unknown) => (error as ApiError)?.message ?? "操作失败，请稍后重试。";

function App() {
  const [activeNav, setActiveNav] = useState<NavKey>("today");
  const pageContentRef = useRef<HTMLDivElement>(null);
  const [bookId, setBookId] = useState<BookId>(books[0].id);
  const [toast, setToast] = useState<Toast>(null);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [taskStates, setTaskStates] = useState<Record<string, TaskStatus>>({});
  const [generatedPlan, setGeneratedPlan] = useState<LearningPlanResult | null>(null);
  const [weeklyPlan, setWeeklyPlan] = useState<WeeklyPlan | null>(null);
  const [weeklyPlanLoading, setWeeklyPlanLoading] = useState(false);
  const taskStartedAt = useRef(new Map<number | string, number>());
  const diagnosticStartedAt = useRef<number | null>(null);
  const diagnosticFinishedAt = useRef<number | null>(null);
  const diagnosticTaskType = useRef("diagnostic");
  const [todayLearning, setTodayLearning] = useState<TodayLearningResponse | null>(null);
  const [planTab, setPlanTab] = useState<"overview" | "knowledge">("overview");
  const [goalLevel, setGoalLevel] = useState("能够独立完成基础练习");

  // Each page starts at the top without remounting its forms or resetting learning state.
  useEffect(() => {
    pageContentRef.current?.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [activeNav, bookId]);

  const [diagnosticStage, setDiagnosticStage] = useState<"question" | "result">("question");
  const [diagnosticIndex, setDiagnosticIndex] = useState(0);
  const [diagnosticAnswers, setDiagnosticAnswers] = useState<Record<string, string>>({});
  const [diagnosticQuestions, setDiagnosticQuestions] = useState<DiagnosticQuestion[]>(() => getBookContent(books[0].id).questions);
  const [skippedQuestions, setSkippedQuestions] = useState<string[]>([]);
  const [diagnosticPaused, setDiagnosticPaused] = useState(false);
  const [diagnosticBusy, setDiagnosticBusy] = useState(false);
  const [diagnosticId, setDiagnosticId] = useState(`demo-${bookId}-diagnostic`);
  // Set only when the diagnosis was opened from a day in the saved seven-day plan.
  // The backend uses this binding to replan only the remaining, uncompleted items.
  const [diagnosticPlanDayId, setDiagnosticPlanDayId] = useState<number | null>(null);
  const [diagnosticResult, setDiagnosticResult] = useState<DiagnosticResult | null>(null);
  const [calibration, setCalibration] = useState<Calibration | null>(null);
  const [calibrationReason, setCalibrationReason] = useState("");

  const [recordFilter, setRecordFilter] = useState<"all" | RecordItem["category"]>("all");
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordPage, setRecordPage] = useState(1);
  const [recordTotal, setRecordTotal] = useState(0);
  const recordPageSize = 4;
  const [qaInput, setQaInput] = useState("");
  const [qaBusy, setQaBusy] = useState(false);
  const [qaError, setQaError] = useState<string | null>(null);
  const [qaMessages, setQaMessages] = useState<QaMessage[]>([]);
  const [qaSources, setQaSources] = useState<Source[]>([]);
  // 该令牌只用于兼容现有接口；持久化上下文由 userId + bookId + reset 标记决定。
  const [qaContextToken, setQaContextToken] = useState<string | null>(null);
  const [qaContextBusy, setQaContextBusy] = useState(false);
  const [qaAnswerMode, setQaAnswerMode] = useState<QaAnswerMode>("direct");
  const [qaLearningTaskId, setQaLearningTaskId] = useState<string | null>(null);

  const currentBook = useMemo(() => books.find((book) => book.id === bookId) ?? books[0], [bookId]);
  const content = useMemo(() => getBookContent(bookId), [bookId]);
  const currentTasks = useMemo(
    () => (generatedPlan?.tasks ?? content.planTasks).map((task) => ({ ...task, status: taskStates[task.id] ?? task.status })),
    [content, generatedPlan, taskStates],
  );
  const currentQuestion = diagnosticQuestions[diagnosticIndex] ?? diagnosticQuestions[0];
  const databaseUserId = useMemo(queryUserId, []);

  const loadRecords = async () => {
    setRecordsLoading(true);
    try {
      const result = await api.getLearningRecords({ category: recordFilter, page: recordPage, pageSize: recordPageSize });
      setRecords(result.records.map(toRecordItem));
      setRecordTotal(result.total);
    } catch (error) {
      setRecords([]);
      showToast("学习记录加载失败", errorMessage(error));
    } finally {
      setRecordsLoading(false);
    }
  };

  const showToast = (title: string, message: string) => {
    setToast({ title, message });
    window.setTimeout(() => setToast(null), 3200);
  };

  const closeModal = () => setModal(null);

  const initializeQaContext = async (nextBookId: BookId, resetContext = false) => {
    setQaContextBusy(true);
    setQaContextToken(null);
    setQaMessages([]);
    setQaSources([]);
    setQaError(null);
    try {
      const context = await api.initializeQaContext(nextBookId, resetContext);
      setQaContextToken(context.conversationId);
      setQaAnswerMode(context.answerMode ?? "direct");
      setQaLearningTaskId(context.learningTaskId ?? null);
      if (resetContext) showToast("已清空对话", "之后的回答不会再使用此前的问答内容。");
    } catch (error) {
      setQaError(errorMessage(error));
    } finally {
      setQaContextBusy(false);
    }
  };

  const clearQaContext = () => {
    if (qaBusy) {
      showToast("暂时不能清空", "请等待当前回答完成后再清空对话。");
      return;
    }
    if (qaContextBusy) return;
    void initializeQaContext(bookId, true);
  };

  const changeQaAnswerMode = async (mode: QaAnswerMode) => {
    if (qaBusy || qaContextBusy) return;
    if (mode === qaAnswerMode) return;
    if (qaLearningTaskId) {
      try {
        await api.finishQaLearningTask(bookId, qaLearningTaskId);
      } catch (error) {
        showToast("切换失败", errorMessage(error));
        return;
      }
    }
    setQaAnswerMode(mode);
    // Choosing a mode starts a fresh teaching task without erasing chat history.
    setQaLearningTaskId(null);
    setQaError(null);
  };

  const finishSocraticTask = async () => {
    if (qaBusy) return;
    if (qaLearningTaskId) {
      try {
        await api.finishQaLearningTask(bookId, qaLearningTaskId);
      } catch (error) {
        showToast("结束引导失败", errorMessage(error));
        return;
      }
    }
    setQaLearningTaskId(null);
    showToast("已结束本轮引导", "下一次提问将开始一个新的学习任务。");
  };

  useEffect(() => {
    void initializeQaContext(books[0].id);
  }, []);

  useEffect(() => {
    void loadRecords();
  }, [bookId, recordFilter, recordPage]);

  useEffect(() => {
    let active = true;
    setWeeklyPlan(null);
    if (!databaseUserId) return () => { active = false; };
    setWeeklyPlanLoading(true);
    void api.getWeeklyLearningPlan(databaseUserId, databaseBookIds[bookId]).then((result) => {
      if (active && result.exists) setWeeklyPlan(result.plan);
    }).catch(() => {
      if (active) setWeeklyPlan(null);
    }).finally(() => { if (active) setWeeklyPlanLoading(false); });
    return () => { active = false; };
  }, [bookId, databaseUserId]);

  useEffect(() => {
    let active = true;
    setTodayLearning(null);
    void api.getTodayLearning(bookId).then((result) => {
      if (active) setTodayLearning(result);
    }).catch(() => {
      if (active) setTodayLearning(null);
    });
    return () => { active = false; };
  }, [bookId]);

  // 书籍目录来自 GET /books（未就绪时服务层自动回退本地目录）。
  useEffect(() => {
    if (!user) return;
    let active = true;
    void api.getBooks()
      .then((result) => { if (active) setBookCatalog(result.books.filter((book) => book.available !== false)); })
      .catch(() => { if (active) setBookCatalog([]); });
    return () => { active = false; };
  }, [user]);

  // 拉取知识点名称，供「学习资源」页把 ID 显示成中文名。
  useEffect(() => {
    if (!user) return;
    let active = true;
    void api.getKnowledgePoints("machine_learning")
      .then((result) => {
        if (!active) return;
        setKnowledgePointNames(Object.fromEntries(result.knowledgePoints.map((point) => [point.id, point.name])));
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [user]);

  // 登录后若尚未建立学习目标，先进入「选书与目标」引导。
  useEffect(() => {
    if (!user) return;
    const saved = readSavedGoal(user.userId);
    if (saved) {
      setBookId(saved.bookId);
      setGoalLevel(saved.targetLevel);
    } else {
      setActiveNav("goals");
    }
  }, [user]);

  const handleAuthenticated = (nextUser: AuthUser) => {
    setUser(nextUser);
    setActiveNav("today");
  };

  /** 侧边栏退出登录：先确认，避免误触丢掉当前会话。 */
  const handleLogoutClick = async () => {
    setModal({
      title: "退出登录",
      subtitle: user ? `当前账号：${user.nickname}（${user.account}）` : undefined,
      content: <p style={{ margin: 0, color: "var(--muted)", fontSize: 12.5, lineHeight: 1.7 }}>
        退出后需要重新登录才能继续学习。想切换到体验账号的话，退出后用 <strong>demo@study.local</strong> / <strong>demo1234</strong> 登录即可。
      </p>,
      secondary: { label: "取消", onClick: closeModal },
      primary: { label: "确认退出", onClick: async () => { closeModal(); await auth.logout(); handleLogout(); } },
    });
  };

  const handleLogout = () => {
    setUser(null);
    setActiveNav("today");
    setGeneratedPlan(null);
    setTodayLearning(null);
    setRecords([]);
  };

  const handleGoalSaved = (result: { bookId: string; targetLevel: string; dailyMinutes: number; targetDate: string; rescheduled?: boolean; estimatedDays?: number | null; planRefreshSuggested?: boolean }) => {
    if (user) {
      try {
        window.localStorage.setItem(goalStorageKey(user.userId), JSON.stringify(result));
      } catch {
        // 本地存储不可用时不阻断流程，仅本次会话生效。
      }
    }
    setGoalLevel(result.targetLevel);
    resetBookState(result.bookId);
    setActiveNav("today");
    // 三种情况分开说，别用一句「已保存」把后端到底做了什么盖住。
    if (result.planRefreshSuggested) {
      showToast(
        "目标水平已更新",
        "任务日期已按新的时长重排。不过目标水平变了，任务内容本身要重做一次诊断才会跟着变——重新生成会清掉当前计划的完成进度，所以交给你决定。",
      );
    } else if (result.rescheduled) {
      showToast(
        "学习目标已保存",
        result.estimatedDays
          ? `已按新的每日时长重排学习计划，预计 ${result.estimatedDays} 天完成。`
          : "已按新的每日时长重排学习计划。",
      );
    } else {
      showToast("学习目标已保存", "可以开始能力诊断，或先查看今日学习。");
    }
  };

  const changeRecordFilter = (filter: "all" | RecordItem["category"]) => {
    setRecordPage(1);
    setRecordFilter(filter);
  };

  const resetBookState = (nextBookId: BookId) => {
    setBookId(nextBookId);
    setTaskStates({});
    setGeneratedPlan(null);
    setPlanTab("overview");
    setDiagnosticStage("question");
    setDiagnosticIndex(0);
    setDiagnosticAnswers({});
    setDiagnosticQuestions(getBookContent(nextBookId).questions);
    setSkippedQuestions([]);
    setDiagnosticPaused(false);
    setDiagnosticId(`demo-${nextBookId}-diagnostic`);
    setDiagnosticPlanDayId(null);
    setDiagnosticResult(null);
    setCalibration(null);
    setCalibrationReason("");
    void initializeQaContext(nextBookId);
    showToast("已切换学习内容", `${getBookContent(nextBookId).goal}的页面内容已更新。`);
  };

  const goTo = (key: NavKey) => {
    if (key === "diagnostic") {
      void startDiagnostic();
      return;
    }
    setActiveNav(key);
  };

  const startDiagnostic = async () => {
    setActiveNav("diagnostic");
    setDiagnosticStage("question");
    setDiagnosticIndex(0);
    setDiagnosticAnswers({});
    setDiagnosticQuestions([]);
    setSkippedQuestions([]);
    setDiagnosticPaused(false);
    // Starting a diagnosis from the navigation should still update the active
    // plan day when a saved plan is available; otherwise it is a standalone diagnosis.
    const today = new Date().toISOString().slice(0, 10);
    const planDay = databaseUserId
      ? weeklyPlan?.days.find((day) => day.expected_date === today && day.items.some((item) => item.status !== "completed"))
        ?? weeklyPlan?.days.find((day) => day.items.some((item) => item.status !== "completed"))
      : undefined;
    const planItem = planDay?.items.find((item) => item.status !== "completed");
    setDiagnosticPlanDayId(planDay?.id ?? null);
    setDiagnosticBusy(true);
    diagnosticStartedAt.current = Date.now();
    diagnosticFinishedAt.current = null;
    diagnosticTaskType.current = "diagnostic";
    try {
      const result = await api.startDiagnostic(bookId, content.goal, databaseUserId ?? undefined, planDay?.id, planItem?.id);
      setDiagnosticId(result.diagnosticId);
      setDiagnosticQuestions(result.questions);
      void api.writeLearningEvent({ taskId: result.diagnosticId, taskTitle: "学习前诊断", eventType: "task_started", status: "in_progress", userId: String(databaseUserId ?? "user_001"), bookId: String(databaseBookIds[bookId]), detail: { task_type: "diagnostic" } });
      showToast("诊断已开始", `共 ${result.questions.length} 道题，答案会逐题保存。`);
    } catch (error) {
      showToast("诊断启动失败", errorMessage(error));
    } finally {
      setDiagnosticBusy(false);
    }
  };

  const advanceDiagnostic = async (question: DiagnosticQuestion, answer?: string, skipped = false) => {
    setDiagnosticBusy(true);
    try {
      await api.submitDiagnosticAnswer(diagnosticId, { questionId: question.id, answer: answer ?? "", skipped });
      if (diagnosticIndex >= diagnosticQuestions.length - 1) {
        const result = await api.finishDiagnostic(diagnosticId);
        diagnosticFinishedAt.current = Date.now();
        await loadRecords();
        setDiagnosticResult(result);
        setDiagnosticStage("result");
        showToast("诊断已完成", "你可以查看评估依据并提交自己的校准。 ");
      } else {
        setDiagnosticIndex((index) => index + 1);
        showToast(skipped ? "已跳过当前题" : "答案已保存", `进入第 ${diagnosticIndex + 2} 题。`);
      }
    } catch (error) {
      showToast("提交失败", errorMessage(error));
    } finally {
      setDiagnosticBusy(false);
    }
  };

  const submitDiagnostic = () => {
    if (!currentQuestion) return;
    const answer = diagnosticAnswers[currentQuestion.id];
    if (!answer) {
      showToast("还没有提交答案", "请选择一个选项后继续诊断。 ");
      return;
    }
    void advanceDiagnostic(currentQuestion, answer);
  };

  const skipDiagnostic = () => {
    if (!currentQuestion) return;
    setSkippedQuestions((items) => [...items, currentQuestion.id]);
    void advanceDiagnostic(currentQuestion, undefined, true);
  };

  const resumeDiagnostic = () => setDiagnosticPaused(false);

  const submitCalibration = async () => {
    if (!calibration) {
      showToast("请选择自我判断", "提交前请先选择与你最接近的能力水平。 ");
      return;
    }
    setDiagnosticBusy(true);
    try {
      // Persist the observed pace first.  The confirmation endpoint immediately
      // re-runs BKT and the future-plan scheduler, so it must see this round's
      // duration in the behavior profile rather than waiting for tomorrow.
      if (diagnosticStartedAt.current) {
        const completedAt = diagnosticFinishedAt.current ?? Date.now();
        await api.writeLearningEvent({ taskId: diagnosticId, taskTitle: "学习答题任务", eventType: "task_completed", status: "completed", userId: String(databaseUserId ?? "user_001"), bookId: String(databaseBookIds[bookId]), detail: { task_type: diagnosticTaskType.current, duration_seconds: Math.max(1, Math.round((completedAt - diagnosticStartedAt.current) / 1000)) } });
        diagnosticStartedAt.current = null;
        diagnosticFinishedAt.current = null;
      }
      await api.submitCalibration({ diagnosticId, level: calibration, reason: calibrationReason });
      await loadRecords();
      if (diagnosticPlanDayId && databaseUserId) {
        const refreshed = await api.getWeeklyLearningPlan(databaseUserId, databaseBookIds[bookId]);
        setWeeklyPlan(refreshed.plan);
        setPlanTab("overview");
        setActiveNav("plan");
        showToast("已确认并更新计划", "已完成任务保持不变，后续待完成任务已按本次答题结果重排。 ");
      } else {
        showToast("诊断结果已确认", "本次答题和校准结果已保存。 ");
      }
    } catch (error) {
      showToast("确认失败", errorMessage(error));
    } finally {
      setDiagnosticBusy(false);
    }
  };

  const updateTask = async (task: LearningTask) => {
    const currentStatus = taskStates[task.id] ?? task.status;
    const nextStatus: TaskStatus = currentStatus === "completed" ? "completed" : currentStatus === "in_progress" ? "completed" : "in_progress";
    const taskIndex = currentTasks.findIndex((item) => item.id === task.id);
    const nextTask = nextStatus === "completed"
      ? currentTasks.slice(taskIndex + 1).find((item) => (taskStates[item.id] ?? item.status) !== "completed")
      : undefined;
    const previousNextStatus = nextTask ? (taskStates[nextTask.id] ?? nextTask.status) : undefined;
    setTaskStates((states) => ({
      ...states,
      [task.id]: nextStatus,
      ...(nextTask ? { [nextTask.id]: "in_progress" as TaskStatus } : {}),
    }));
    try {
      if (nextStatus === "completed") {
        await api.writeLearningEvent({ taskId: task.id, taskTitle: task.title, eventType: "task_completed", status: nextStatus });
      }
      await loadRecords();
      showToast(nextStatus === "completed" ? "任务已完成" : "任务已开始", nextStatus === "completed" ? "下一项学习任务已经准备好。" : "完成后可以继续更新学习进度。 ");
    } catch (error) {
      setTaskStates((states) => ({
        ...states,
        [task.id]: currentStatus,
        ...(nextTask && previousNextStatus ? { [nextTask.id]: previousNextStatus } : {}),
      }));
      showToast("任务更新失败", errorMessage(error));
    }
  };

  const openTask = (task: LearningTask) => {
    const status = taskStates[task.id] ?? task.status;
    setModal({
      title: task.title,
      subtitle: `${task.type} · ${task.minutes} 分钟 · ${statusLabels[status]}`,
      content: <div className="task-detail"><p>{task.description}</p><div className="detail-grid"><span>学习目标</span><strong>{task.learningGoal ?? content.goal}</strong><span>推荐理由</span><strong>{task.reason}</strong></div></div>,
      secondary: { label: "关闭", onClick: closeModal },
      primary: status === "completed" ? undefined : { label: status === "in_progress" ? "完成任务" : "开始任务", onClick: () => { closeModal(); void updateTask(task); } },
    });
  };

  const startPlanDiagnostic = (dayId: number, itemId: number, taskType = "diagnostic") => {
    if (!databaseUserId) {
      showToast("缺少用户 ID", "请在地址栏添加 ?user_id=你的数字用户ID 后启动每日诊断。");
      return;
    }
    closeModal();
    taskStartedAt.current.set(itemId, Date.now());
    void startDiagnosticForPlanDay(dayId, itemId, taskType);
  };

  const startDiagnosticForPlanDay = async (dayId: number, itemId: number, taskType = "diagnostic") => {
    setActiveNav("diagnostic");
    setDiagnosticStage("question"); setDiagnosticIndex(0); setDiagnosticAnswers({}); setDiagnosticQuestions([]); setSkippedQuestions([]); setDiagnosticPaused(false); setDiagnosticBusy(true);
    setDiagnosticPlanDayId(dayId);
    diagnosticStartedAt.current = Date.now();
    diagnosticFinishedAt.current = null;
    diagnosticTaskType.current = taskType;
    try {
      const result = await api.startDiagnostic(bookId, content.goal, databaseUserId ?? undefined, dayId, itemId);
      setDiagnosticId(result.diagnosticId); setDiagnosticQuestions(result.questions);
      void api.writeLearningEvent({ taskId: result.diagnosticId, taskTitle: "学习答题任务", eventType: "task_started", status: "in_progress", userId: String(databaseUserId ?? "user_001"), bookId: String(databaseBookIds[bookId]), detail: { task_type: taskType } });
      showToast("每日诊断已开始", "完成后会更新掌握度，并重排尚未开始的计划内容。");
    } catch (error) { showToast("诊断启动失败", errorMessage(error)); } finally { setDiagnosticBusy(false); }
  };

  const completeWeeklyPlanItem = async (item: WeeklyPlanItem) => {
    if (!databaseUserId) {
      showToast("缺少用户 ID", "请在地址栏添加 ?user_id=你的数字用户ID 后完成阅读任务。");
      return;
    }
    setWeeklyPlanLoading(true);
    try {
      const startedAt = taskStartedAt.current.get(item.id) ?? Date.now();
      await api.writeLearningEvent({ taskId: String(item.id), taskTitle: item.title, eventType: "task_completed", status: "completed", userId: String(databaseUserId), bookId: String(databaseBookIds[bookId]), detail: { task_type: item.title.startsWith("阅读：") ? "reading" : item.title.startsWith("复习：") ? "review" : "practice", duration_seconds: Math.max(1, Math.round((Date.now() - startedAt) / 1000)) } });
      await api.completeWeeklyPlanItem(item.id, databaseUserId);
      const refreshed = await api.getWeeklyLearningPlan(databaseUserId, databaseBookIds[bookId]);
      setWeeklyPlan(refreshed.plan);
      closeModal();
      showToast("阅读任务已完成", "已保存到数据库，后续计划不会改动这条已完成任务。");
    } catch (error) {
      showToast("阅读任务更新失败", errorMessage(error));
    } finally {
      setWeeklyPlanLoading(false);
    }
  };

  const isWeeklyItemUnlocked = (itemId: number) => {
    const items = weeklyPlan?.days.flatMap((day) => day.items) ?? [];
    const firstPending = items.find((item) => item.status !== "completed");
    return !firstPending || firstPending.id === itemId;
  };

  const openWeeklyItem = (item: WeeklyPlanItem, dayId: number, date: string) => {
    if (item.status !== "completed" && !isWeeklyItemUnlocked(item.id)) {
      showToast("任务尚未解锁", "请先完成计划中的上一个任务。");
      return;
    }
    const isQuestion = item.source === "review_due" || item.source === "spaced_review" || item.title.startsWith("学习前诊断") || item.title.startsWith("练习：") || item.title.startsWith("复习：");
    if (isQuestion) {
      const taskType = item.title.startsWith("练习：") ? "practice" : item.title.startsWith("复习：") ? "review" : "diagnostic";
      setModal({ title: item.title, subtitle: `${date} · 答题任务`, content: <div className="task-detail"><p>{item.description}</p><div className="detail-grid"><span>任务类型</span><strong>能力诊断 / 知识点练习</strong><span>安排原因</span><strong>{item.adaptive_reason}</strong></div></div>, secondary: { label: "稍后再做", onClick: closeModal }, primary: item.status === "completed" ? undefined : { label: "开始答题", onClick: () => startPlanDiagnostic(dayId, item.id, taskType) } });
      return;
    }
    setModal({ title: item.title, subtitle: `${date} · 教材阅读`, content: <div className="typing-state">正在读取本地教材并检索网络参考资料…</div>, secondary: { label: "关闭", onClick: closeModal } });
    void api.getReadingMaterials(databaseBookIds[bookId], item.title).then((materials) => {
      if (item.status !== "completed") {
        taskStartedAt.current.set(item.id, Date.now());
        void api.writeLearningEvent({ taskId: String(item.id), taskTitle: item.title, eventType: "task_started", status: "in_progress", userId: String(databaseUserId ?? "user_001"), bookId: String(databaseBookIds[bookId]), detail: { task_type: "reading" } });
      }
      setModal({ title: "阅读内容", content: <ReadingMaterialDialog materials={materials} />, secondary: { label: "关闭", onClick: closeModal }, primary: item.status === "completed" ? undefined : { label: "完成阅读", onClick: () => { void completeWeeklyPlanItem(item); } } });
    }).catch((error) => {
      setModal({ title: item.title, subtitle: `${date} · 教材阅读`, content: <div className="task-detail"><p>{item.description}</p><div className="inline-error"><Icon name="info" size={16} /><span>{errorMessage(error)}</span></div></div>, secondary: { label: "关闭", onClick: closeModal } });
    });
  };

  const generateWeeklyPlan = async () => {
    if (!databaseUserId) { showToast("缺少用户 ID", "请在地址栏添加 ?user_id=你的数字用户ID 后生成并读取数据库计划。"); return; }
    setWeeklyPlanLoading(true);
    try {
      const plan = await api.generateWeeklyLearningPlan(databaseUserId, databaseBookIds[bookId]);
      const loaded = await api.getWeeklyLearningPlan(databaseUserId, databaseBookIds[bookId]);
      setWeeklyPlan(loaded.plan ?? plan); setPlanTab("overview");
      showToast("七天计划已生成", "已写入数据库，并按每天的诊断、阅读和练习任务展示。");
    } catch (error) { showToast("生成计划失败", errorMessage(error)); } finally { setWeeklyPlanLoading(false); }
  };

  const openKnowledgeDetail = () => setModal({
    title: "能力图谱详情",
    subtitle: `${currentBook.title} · ${content.goal}`,
    content: <div className="dialog-list">{content.nodes.map((node) => <div className="dialog-list-item" key={node.label}><span className={`dot ${node.tone === "good" ? "green" : node.tone === "weak" ? "amber" : "blue"}`} /><div><strong>{node.label}</strong><p>{node.description}</p></div></div>)}</div>,
    secondary: { label: "关闭", onClick: closeModal },
  });

  const openEvidence = () => setModal({
    title: "诊断依据详情",
    subtitle: "AI 判断与用户校准分别记录",
    content: <div className="dialog-list"><div className="dialog-list-item"><Icon name="target" size={17} /><div><strong>作答表现</strong><p>{diagnosticResult?.answerPerformance ?? "暂无作答表现。"}</p></div></div><div className="dialog-list-item"><Icon name="clock" size={17} /><div><strong>判断时间</strong><p>{diagnosticResult?.generatedAt ? new Date(diagnosticResult.generatedAt).toLocaleString() : "暂无判断时间。"}</p></div></div><div className="dialog-list-item"><Icon name="file" size={17} /><div><strong>关联范围</strong><p>{diagnosticResult?.relatedScope ?? `${content.goal}及其前置知识点。`}</p></div></div></div>,
    secondary: { label: "关闭", onClick: closeModal },
  });

  const openGoalEditor = () => setModal({
    title: "调整学习目标",
    subtitle: "调整后会交给后端重新生成任务排序",
    content: <GoalEditor initialValue={goalLevel} onSave={(value) => { setGoalLevel(value); closeModal(); showToast("目标已调整", "下一次生成计划时会使用新的目标水平。 "); }} />,
    secondary: { label: "取消", onClick: closeModal },
  });

  const openRecord = (record: RecordItem) => setModal({
    title: "记录详情",
    subtitle: record.time,
    content: <div className="task-detail"><p>{record.title}</p><div className="detail-grid"><span>事件描述</span><strong>{record.description}</strong><span>关联内容</span><strong>{content.goal}</strong><span>数据来源</span><strong>学习事件记录</strong></div></div>,
    secondary: { label: "关闭", onClick: closeModal },
  });

  const sourceBookTitle = (source: Source) => books.find((item) => item.id === source.bookId)?.title ?? currentBook.title;
  const sourceDisplayTitle = (source: Source) => `${sourceBookTitle(source)} · ${source.contentUnitId || source.title}`;
  const openSource = (source: Source) => setModal({
    title: "资料来源",
    subtitle: `${sourceBookTitle(source)} · ${source.location}`,
    content: <div className="source-preview"><span className="source-type">{source.type}</span><h3>{sourceDisplayTitle(source)}</h3><p>{source.excerpt}</p><div className="source-location"><Icon name="file" size={15} />定位：{source.location}</div></div>,
    secondary: { label: "关闭", onClick: closeModal },
  });

  const openMaterialPlanEditor = () => setModal({
    title: "加入学习计划",
    subtitle: "填写这次资料问答对应的学习任务",
    content: <MaterialPlanEditor onSave={async (payload) => {
      try {
        const plan = await api.createMaterialPlan({ ...payload, bookId, resources: qaSources });
        setGeneratedPlan(plan);
        setPlanTab("overview");
        closeModal();
        goTo("plan");
        showToast("已加入学习计划", "资料问答任务已经创建。 ");
      } catch (error) {
        showToast("加入学习计划失败", errorMessage(error));
      }
    }} />,
    secondary: { label: "取消", onClick: closeModal },
  });

  const askQuestion = async () => {
    const question = qaInput.trim();
    if (!question || qaBusy || qaContextBusy) {
      if (!question) showToast("请输入问题", "输入问题后再发送。 ");
      return;
    }
    if (!qaContextToken) {
      setQaError("问答会话尚未创建完成，请稍后重试。");
      return;
    }
    setQaInput("");
    setQaError(null);
    setQaMessages((messages) => [...messages, { role: "user", text: question }]);
    setQaBusy(true);
    try {
      const result = await api.askQuestion({ bookId, question, conversationId: qaConversationId, sources: content.sources });
      setQaSources(result.citations);
      setQaMessages((messages) => [...messages, { role: "assistant", text: question.includes("过拟合") ? content.qaAnswer : result.answer, citations: result.citations }]);
      setQaMessages((messages) => [...messages.slice(0, -1), { role: "assistant", text: result.answer, citations: result.citations }]);
      const result = await api.askQuestion({
        bookId,
        question,
        conversationId: qaContextToken ?? undefined,
        sources: content.sources,
        allowGeneralFallback,
        answerMode: allowGeneralFallback ? "direct" : qaAnswerMode,
        learningTaskId: allowGeneralFallback ? null : qaLearningTaskId,
      });
      if (!result.refused) setQaSources(result.citations);
      const fromGeneralModel = Boolean(result.answeredByGeneralModel) || (allowGeneralFallback && !result.refused && result.citations.length === 0);
      setQaMessages((messages) => [...messages, {
        role: "assistant",
        text: result.answer,
        citations: result.refused ? [] : result.citations,
        refused: result.refused,
        fromGeneralModel,
        question,
        answerMode: result.answerMode ?? qaAnswerMode,
        socraticState: result.socraticState,
        responseQuality: result.responseQuality,
        socraticCompleted: result.socraticCompleted,
      }]);
      if (result.answerMode === "socratic") {
        setQaLearningTaskId(result.socraticCompleted ? null : (result.learningTaskId ?? null));
        if (result.socraticCompleted) showToast("本轮引导已完成", "你已经通过了迁移验证，可以开始新的问题。");
      }
      if (allowGeneralFallback && result.refused) {
        // 后端尚未实现 allowGeneralFallback 时会再次拒答，如实告知而不是静默失败。
        setQaError("后端暂不支持通用模型回答（需实现 allowGeneralFallback 参数）。");
      }
    } catch (error) {
      setQaError(errorMessage(error));
    } finally {
      setQaBusy(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup"><div className="brand-mark"><Icon name="book-open" size={22} /></div><div><strong>自适应伴学智能体</strong><span>学习闭环</span></div></div>
        <nav className="main-nav" aria-label="主导航">{navigation.map((item) => <button className={`nav-item ${activeNav === item.key ? "active" : ""}`} key={item.key} onClick={() => goTo(item.key)}><Icon name={item.icon} size={19} /><span>{item.label}</span></button>)}</nav>
        <div className="sidebar-bottom"><button className="nav-item" onClick={() => setModal({ title: "设置", subtitle: "用户偏好与学习提醒", content: <div className="dialog-list"><div className="dialog-list-item"><Icon name="clock" size={17} /><div><strong>学习时间</strong><p>后端接入后可保存每周学习时长和提醒时间。</p></div></div><div className="dialog-list-item"><Icon name="target" size={17} /><div><strong>目标偏好</strong><p>可从学习计划页面调整当前目标水平。</p></div></div></div>, secondary: { label: "关闭", onClick: closeModal } })}><Icon name="settings" size={19} /><span>设置</span></button><button className="nav-item" onClick={() => setModal({ title: "帮助中心", subtitle: "自适应伴学智能体使用说明", content: <div className="dialog-list"><div className="dialog-list-item"><Icon name="book" size={17} /><div><strong>先选择学习内容</strong><p>当前支持机器学习和深度学习，后续可以继续增加书籍。</p></div></div><div className="dialog-list-item"><Icon name="target" size={17} /><div><strong>再完成能力诊断</strong><p>诊断结果和用户校准会共同影响学习计划。</p></div></div></div>, secondary: { label: "关闭", onClick: closeModal } })}><Icon name="help" size={19} /><span>帮助</span></button></div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div className="mobile-brand"><div className="brand-mark"><Icon name="book-open" size={20} /></div></div><div className="topbar-context"><span className="context-label">当前学习内容</span><label className="book-select"><Icon name="book" size={18} /><select value={bookId} onChange={(event) => resetBookState(event.target.value as BookId)} aria-label="选择当前学习内容">{books.map((book) => <option key={book.id} value={book.id}>{book.title}</option>)}</select><Icon name="chevron-down" size={15} /></label></div></header>
        {activeNav === "today" && <TodayView book={currentBook} content={content} tasks={currentTasks} dashboard={todayLearning} goTo={goTo} startDiagnostic={startDiagnostic} onOpenTask={openTask} onOpenKnowledge={openKnowledgeDetail} onOpenRecords={() => goTo("records")} />}
        <nav className="main-nav" aria-label="主导航">{navigation.map((item) => <button className={`nav-item ${activeNav === item.key ? "active" : ""}`} key={item.key} aria-label={item.label} title={item.label} onClick={() => goTo(item.key)}><Icon name={item.icon} size={19} /><span>{item.label}</span></button>)}</nav>
        <div className="sidebar-bottom"><button className={`nav-item ${activeNav === "goals" ? "active" : ""}`} onClick={() => setActiveNav("goals")}><Icon name="target" size={19} /><span>选书与目标</span></button><button className={`nav-item ${activeNav === "settings" ? "active" : ""}`} onClick={() => setActiveNav("settings")}><Icon name="settings" size={19} /><span>设置</span></button><button className={`nav-item ${activeNav === "help" ? "active" : ""}`} onClick={() => setActiveNav("help")}><Icon name="help" size={19} /><span>帮助</span></button>
          <div className="sidebar-user">
            <button className="sidebar-user-main" onClick={() => setActiveNav("settings")} title="账户设置">
              <span className="sidebar-avatar">{user.nickname.slice(0, 1).toUpperCase()}</span>
              <span className="sidebar-user-meta"><strong>{user.nickname}</strong><span>{user.account}</span></span>
            </button>
            <button className="sidebar-logout" onClick={() => void handleLogoutClick()} title="退出登录" aria-label="退出登录">
              <Icon name="log-out" size={16} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <div className="page-content" ref={pageContentRef} role="region" aria-label="页面内容" tabIndex={0}>
        <header className="topbar"><div className="mobile-brand"><div className="brand-mark"><Icon name="book-open" size={20} /></div></div><div className="topbar-context"><span className="context-label">当前学习内容</span><label className="book-select"><Icon name="book" size={18} /><select value={bookId} onChange={(event) => resetBookState(event.target.value as BookId)} aria-label="选择当前学习内容">{bookOptions.map((book) => <option key={book.id} value={book.id}>{book.title}</option>)}</select><Icon name="chevron-down" size={15} /></label></div></header>
        <div className="page-body">
        {activeNav === "today" && <TodayView book={currentBook} content={content} tasks={currentTasks} dashboard={todayDashboard} goTo={goTo} startDiagnostic={startDiagnostic} onOpenTask={openTask} onOpenKnowledge={openKnowledgeDetail} onOpenRecords={() => goTo("records")} />}
        {activeNav === "profile" && <LearnerProfileView bookId={bookId} />}
        {activeNav === "diagnostic" && <DiagnosticView questions={diagnosticQuestions} index={diagnosticIndex} answers={diagnosticAnswers} skippedQuestions={skippedQuestions} paused={diagnosticPaused} busy={diagnosticBusy} stage={diagnosticStage} result={diagnosticResult} calibration={calibration} calibrationReason={calibrationReason} updatesPlan={Boolean(diagnosticPlanDayId)} setAnswer={(id) => currentQuestion && setDiagnosticAnswers((answers) => ({ ...answers, [currentQuestion.id]: id }))} onPrevious={() => setDiagnosticIndex((index) => Math.max(0, index - 1))} onSubmit={submitDiagnostic} onSkip={skipDiagnostic} onPause={() => setDiagnosticPaused(true)} onResume={resumeDiagnostic} onCalibration={setCalibration} onReason={setCalibrationReason} onEvidence={openEvidence} onCalibrationSubmit={submitCalibration} />}
        {activeNav === "plan" && (weeklyPlan ? <WeeklyPlanView plan={weeklyPlan} book={currentBook} onOpenItem={openWeeklyItem} isUnlocked={isWeeklyItemUnlocked} onRegenerate={() => void generateWeeklyPlan()} busy={weeklyPlanLoading} /> : <PlanEmptyView onStartDiagnostic={startDiagnostic} onGenerate={() => void generateWeeklyPlan()} hasUser={Boolean(databaseUserId)} busy={weeklyPlanLoading} />)}
        {activeNav === "records" && <RecordsView records={records} total={recordTotal} page={recordPage} pageSize={recordPageSize} loading={recordsLoading} filter={recordFilter} setFilter={changeRecordFilter} onPageChange={setRecordPage} onOpenRecord={openRecord} onReview={() => startDiagnostic()} />}
        {activeNav === "qa" && <QaView book={currentBook} sources={qaSources} messages={qaMessages} value={qaInput} busy={qaBusy} error={qaError} onChange={setQaInput} onAsk={askQuestion} onNew={() => void initializeQaConversation(bookId)} onOpenSource={openSource} onAddPlan={openMaterialPlanEditor} />}
        {activeNav === "goals" && <GoalsSetupView initialBookId={bookId} onSaved={handleGoalSaved} onSkip={() => setActiveNav("today")} />}
        {activeNav === "settings" && <SettingsView user={user} onUserUpdated={setUser} onLogout={handleLogout} />}
        {activeNav === "resources" && <LearningResourcesView knowledgePointNames={knowledgePointNames} />}
        {activeNav === "help" && <HelpCenterView onNavigate={goTo} />}
        {activeNav === "community" && <CommunityView key={user.userId} userId={user.userId} nickname={user.nickname} course={currentBook.shortTitle} />}
        {activeNav === "qa" && <QaView book={currentBook} sources={qaSources} messages={qaMessages} value={qaInput} busy={qaBusy} error={qaError} onChange={setQaInput} onAsk={askQuestion} onNew={() => void initializeQaConversation(bookId)} onOpenSource={openSource} onAddPlan={openMaterialPlanEditor} onAskGeneral={askWithGeneralModel} relatedKnowledgePointIds={(todayLearning?.knowledgeGraph.nodes ?? []).filter((node) => node.status === "weak").map((node) => node.id)} />}
        </div>
        </div>
      </main>

      {toast && <div className="toast" role="status"><div className="toast-icon"><Icon name="check" size={17} /></div><div><strong>{toast.title}</strong><span>{toast.message}</span></div></div>}
      {modal && <Modal modal={modal} onClose={closeModal} />}
    </div>
  );
}

function buildMessages(content: ReturnType<typeof getBookContent>): QaMessage[] {
  return [{ role: "user", text: content.qaQuestion }, { role: "assistant", text: content.qaAnswer, citations: content.sources }];
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="page-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}

function PlanEmptyView({ onStartDiagnostic, onGenerate, hasUser, busy }: { onStartDiagnostic: () => void; onGenerate: () => void; hasUser: boolean; busy: boolean }) {
  return <div className="page-stack"><PageHeader eyebrow="学习闭环 · 目标到任务" title="学习计划" description="系统从 MySQL 的学习目标、当前掌握度和目标掌握度生成连续七天的计划。" /><article className="card empty-state"><Icon name="calendar" size={21} /><strong>{hasUser ? "暂时没有学习计划" : "请先指定用户 ID"}</strong><span>{hasUser ? "确认用户画像已保存后，即可生成七天计划。" : "在地址栏添加 ?user_id=你的数字用户ID，页面才会读取该用户的数据库计划。"}</span>{hasUser ? <button className="primary-button" disabled={busy} onClick={onGenerate}>{busy ? "正在生成…" : "生成七天计划"}</button> : <button className="secondary-button" onClick={onStartDiagnostic}>查看能力诊断</button>}</article></div>;
}

function TodayView({ book, content, tasks, dashboard, goTo, startDiagnostic, onOpenTask, onOpenKnowledge, onOpenRecords }: { book: Book; content: ReturnType<typeof getBookContent>; tasks: LearningTask[]; dashboard: TodayLearningResponse | null; goTo: (key: NavKey) => void; startDiagnostic: () => void; onOpenTask: (task: LearningTask) => void; onOpenKnowledge: () => void; onOpenRecords: () => void }) {
  if (dashboard) {
    const continueTask = dashboard.tasks.find((task) => task.status === "in_progress") ?? dashboard.tasks.find((task) => task.status === "todo");
    const nodePositions = [
      { left: "8%", top: "17%" },
      { left: "67%", top: "17%" },
      { left: "5%", top: "49%" },
      { left: "72%", top: "49%" },
      { left: "8%", top: "78%" },
      { left: "69%", top: "78%" },
    ];
    const continueAction = (key: NavKey) => {
      if (key === "plan" && continueTask) {
        onOpenTask(continueTask);
        return;
      }
      goTo(key);
    };
    const dashboardContent = {
      ...content,
      goal: dashboard.goal || content.goal,
      lastLearned: dashboard.continueLearning ? `正在进行：${dashboard.continueLearning.title}` : dashboard.lastLearned || content.lastLearned,
      recommendation: dashboard.recommendation ?? content.recommendation,
      weeklyProgress: dashboard.weeklyProgress,
      nodes: dashboard.knowledgeGraph.nodes.map((node, index) => ({ label: node.label, tone: node.status === "weak" ? "weak" as const : node.status === "good" ? "good" as const : "learning" as const, ...(nodePositions[index % nodePositions.length]), description: node.description })),
    };
    return <LegacyTodayView book={book} content={dashboardContent} tasks={dashboard.tasks} goTo={continueAction} startDiagnostic={startDiagnostic} onOpenTask={onOpenTask} onOpenKnowledge={onOpenKnowledge} onOpenRecords={onOpenRecords} />;
  }
  return <LegacyTodayView book={book} content={content} tasks={tasks} goTo={goTo} startDiagnostic={startDiagnostic} onOpenTask={onOpenTask} onOpenKnowledge={onOpenKnowledge} onOpenRecords={onOpenRecords} />;
}

function LegacyTodayView({ book, content, tasks, goTo, startDiagnostic, onOpenTask, onOpenKnowledge, onOpenRecords }: { book: Book; content: ReturnType<typeof getBookContent>; tasks: LearningTask[]; goTo: (key: NavKey) => void; startDiagnostic: () => void; onOpenTask: (task: LearningTask) => void; onOpenKnowledge: () => void; onOpenRecords: () => void }) {
  const completed = tasks.filter((task) => task.status === "completed").length;
  const weekly = (content as ReturnType<typeof getBookContent> & { weeklyProgress?: TodayLearningResponse["weeklyProgress"] }).weeklyProgress ?? { progressPercent: 68, completedTaskCount: completed + 9, totalTaskCount: 18, studyDurationHours: 6.2, accuracy: 74 };
  return <div className="page-stack"><PageHeader eyebrow="持续学习，循序提升" title="今日学习" description={`${book.title} · ${book.subtitle} · 本周已学习 6.2 小时`} /><section className="stat-grid"><article className="card progress-card"><div className="card-heading"><span>本周进度</span><Icon name="more" size={18} /></div><div className="progress-content"><div className="ring-progress"><span>68<small>%</small></span></div><div className="progress-facts"><div><strong>{completed + 9}/18</strong><span>已完成任务</span></div><div><strong>6.2 h</strong><span>学习时长</span></div><div><strong>74%</strong><span>正确率</span></div></div></div><div className="mini-bars" aria-label="本周学习时长趋势">{[35, 52, 42, 71, 58, 84, 48].map((height, index) => <i style={{ height: `${height}%` }} key={index} />)}</div><div className="week-labels"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div></article><article className="card recommend-card"><div className="card-heading"><span>今日推荐任务</span><span className="status-pill success">最需要提升</span></div><h2>{content.recommendation.title}</h2><div className="task-meta"><span><Icon name="clock" size={14} />预计用时 {content.recommendation.minutes} 分钟</span><span>难度 {content.recommendation.difficulty}</span></div><button className="primary-button" onClick={() => goTo("plan")}>开始学习 <Icon name="arrow-right" size={16} /></button><div className="recommend-reason"><strong>为什么推荐</strong><p>{content.recommendation.reason}</p><button onClick={startDiagnostic}>开始诊断 <Icon name="arrow-up-right" size={14} /></button></div></article><article className="card continue-card"><div className="card-heading"><span>继续学习</span><Icon name="spark" size={18} /></div><div className="target-icon"><Icon name="target" size={23} /></div><h2>{content.goal}</h2><p>上次学习到：{content.lastLearned}</p><button className="outline-button" onClick={() => goTo("plan")}>继续学习</button><button className="text-button" onClick={onOpenRecords}>查看学习记录 <Icon name="arrow-right" size={14} /></button></article></section><section className="dashboard-grid"><article className="card knowledge-card"><div className="card-heading"><div><span>能力图谱</span><small>当前学习目标关联的知识点</small></div><div className="legend"><span><i className="dot green" />掌握良好</span><span><i className="dot blue" />正在学习</span><span><i className="dot amber" />薄弱</span></div></div><div className="knowledge-map"><div className="knowledge-core">{content.goal}</div>{content.nodes.map((node) => <div className={`knowledge-node ${node.tone}`} style={{ left: node.left, top: node.top }} key={node.label}>{node.label}</div>)}</div><button className="secondary-button" onClick={onOpenKnowledge}>查看图谱详情 <Icon name="arrow-right" size={15} /></button></article><article className="card task-card"><div className="card-heading"><span>今日任务</span><span className="completion">{completed}/{tasks.length} 已完成</span></div><div className="task-list">{tasks.map((task) => <TaskRow task={task} key={task.id} onOpen={() => onOpenTask(task)} />)}</div><button className="secondary-button full" onClick={() => goTo("plan")}>查看完整计划 <Icon name="arrow-right" size={15} /></button></article></section></div>;
}

function DiagnosticView({ questions, index, answers, skippedQuestions, paused, busy, stage, result, calibration, calibrationReason, updatesPlan, setAnswer, onPrevious, onSubmit, onSkip, onPause, onResume, onCalibration, onReason, onEvidence, onCalibrationSubmit }: { questions: DiagnosticQuestion[]; index: number; answers: Record<string, string>; skippedQuestions: string[]; paused: boolean; busy: boolean; stage: "question" | "result"; result: DiagnosticResult | null; calibration: Calibration | null; calibrationReason: string; updatesPlan: boolean; setAnswer: (id: string) => void; onPrevious: () => void; onSubmit: () => void; onSkip: () => void; onPause: () => void; onResume: () => void; onCalibration: (value: Calibration) => void; onReason: (value: string) => void; onEvidence: () => void; onCalibrationSubmit: () => void }) {
  if (stage === "result") return <DiagnosticResult result={result} calibration={calibration} reason={calibrationReason} updatesPlan={updatesPlan} busy={busy} onCalibration={onCalibration} onReason={onReason} onEvidence={onEvidence} onSubmit={onCalibrationSubmit} />;
  const question = questions[index];
  if (!question && busy) return <div className="page-stack narrow-page"><PageHeader eyebrow="正在准备" title="正在加载诊断题目" description="系统正在根据当前学习计划与知识点准备题目，请稍候。" /><article className="card empty-state"><div className="typing-state">正在加载题目…</div></article></div>;
  if (!question) return <div className="page-stack narrow-page"><PageHeader title="暂无诊断题目" description="后端当前没有返回可用的诊断题目。" /><article className="card empty-state"><p>请稍后重新开始诊断。</p></article></div>;
  if (paused) return <div className="page-stack narrow-page"><PageHeader eyebrow="诊断已暂停" title="稍后继续诊断" description="已保存的答案不会丢失，回来后可以从当前题目继续。" /><article className="card pause-card"><div className="pause-icon"><Icon name="clock" size={25} /></div><h2>当前进度：第 {index + 1} / {questions.length} 题</h2><p>已完成 {Object.keys(answers).length} 题，跳过 {skippedQuestions.length} 题。</p><button className="primary-button" onClick={onResume}>继续诊断 <Icon name="arrow-right" size={16} /></button></article></div>;
  return <div className="page-stack narrow-page"><PageHeader eyebrow={`诊断会话 · 第 ${index + 1}/${questions.length} 题`} title="能力诊断" description="用少量题目了解当前基础，结果会生成可解释的学习建议。" action={<button className="text-button" onClick={onPause}><Icon name="clock" size={15} />暂时离开</button>} /><div className="diagnostic-progress"><span style={{ width: `${((index + 1) / questions.length) * 100}%` }} /><b>{index + 1} / {questions.length}</b></div><article className="card question-card"><div className="question-top"><span className="question-type">单选题</span><span className="question-tag">{question.tag}</span></div><h2>{question.title}</h2><div className="answer-list">{question.options.map((option) => <button className={`answer-option ${answers[question.id] === option.id ? "selected" : ""}`} key={option.id} onClick={() => setAnswer(option.id)}><span className="option-key">{option.id}</span><span>{option.text}</span>{answers[question.id] === option.id && <Icon name="check-circle" size={18} />}</button>)}</div><div className="question-actions"><div className="question-left-actions"><button className="text-button" disabled={index === 0 || busy} onClick={onPrevious}>上一题</button><button className="text-button" disabled={busy} onClick={onSkip}>跳过</button></div><button className="primary-button" disabled={busy} onClick={onSubmit}>{busy ? "正在保存…" : index === questions.length - 1 ? "提交诊断" : "提交并继续"} <Icon name="arrow-right" size={16} /></button></div></article><div className="info-banner"><Icon name="info" size={18} /><span>答案会逐题保存，诊断完成后可以查看判断依据。{skippedQuestions.length > 0 && ` 已跳过 ${skippedQuestions.length} 题。`}</span></div></div>;
}

function DiagnosticResult({ result, calibration, reason, updatesPlan, busy, onCalibration, onReason, onEvidence, onSubmit }: { result: DiagnosticResult | null; calibration: Calibration | null; reason: string; updatesPlan: boolean; busy: boolean; onCalibration: (value: Calibration) => void; onReason: (value: string) => void; onEvidence: () => void; onSubmit: () => void }) {
  const description = updatesPlan
    ? "确认后会重排当前七天计划中未完成的后续任务；已经完成的任务保持不变。"
    : "确认后会保存本次答题与自我校准结果。";
  return <div className="page-stack"><PageHeader eyebrow="诊断完成" title="测评结果与校准" description={description} action={<span className="status-pill success"><Icon name="check" size={14} />已完成</span>} /><section className="result-grid"><article className="card result-card"><div className="card-heading"><span>AI 评估结果</span><Icon name="spark" size={18} /></div><div className="result-level"><span>能力水平</span><strong>{result?.level ?? "中等偏上"}</strong></div><div className="level-scale"><i style={{ left: "60%" }} /><span>薄弱</span><span>中等</span><span>优秀</span></div><div className="result-metrics"><div><strong>{result?.accuracy ?? "75%"}</strong><span>正确率</span></div><div><strong>{result?.confidence ?? "高"}</strong><span>置信度</span></div></div><div className="evidence-summary"><Icon name="file" size={16} /><div><strong>主要依据</strong><p>{result?.evidence ?? "题目作答结果以及关联知识点表现。"}</p></div></div><button className="secondary-button full" onClick={onEvidence}>查看全部依据 <Icon name="arrow-right" size={15} /></button></article><article className="card result-card calibration-card"><div className="card-heading"><span>用户校准</span><span className="status-pill blue">独立记录</span></div><p className="calibration-intro">你认为自己的真实水平是：</p><div className="calibration-options">{([ ["lower", "低于判断", "我还不太熟悉"], ["same", "基本符合", "这个判断比较准确"], ["higher", "高于判断", "我在其他场景用过"] ] as const).map(([key, title, description]) => <button className={`calibration-option ${calibration === key ? "selected" : ""}`} key={key} onClick={() => onCalibration(key)}><span className="radio-dot" /><div><strong>{title}</strong><small>{description}</small></div>{calibration === key && <Icon name="check-circle" size={18} />}</button>)}</div><label className="reason-input"><span>补充原因（可选）</span><textarea value={reason} onChange={(event) => onReason(event.target.value)} placeholder="例如：我在项目中使用过类似方法。" rows={3} /></label><button className="primary-button full" disabled={!calibration || busy} onClick={onSubmit}>{busy ? "正在确认…" : "确认"} <Icon name="arrow-right" size={16} /></button></article></section></div>;
}

function PlanView({ book, goal, goalLevel, tasks, advice, resources, tab, setTab, onOpenTask, onAdjustGoal, onOpenSource }: { book: { title: string; shortTitle: string }; goal: string; goalLevel: string; tasks: LearningTask[]; advice: string[]; resources: Source[]; tab: "overview" | "knowledge"; setTab: (tab: "overview" | "knowledge") => void; onOpenTask: (task: LearningTask) => void; onAdjustGoal: () => void; onOpenSource: (source: Source) => void }) {
  const completed = tasks.filter((task) => task.status === "completed").length;
  return <div className="page-stack">
    <PageHeader eyebrow="学习闭环 · 目标到任务" title="学习计划" description={book.title} action={<button className="outline-button" onClick={onAdjustGoal}>调整目标</button>} />
    <section className="plan-layout">
      <article className="card plan-summary"><span className="section-label">计划目标</span><h2>{goal}</h2><p>{goalLevel}</p><div className="ring-progress small"><span>{tasks.length ? Math.round((completed / tasks.length) * 100) : 0}<small>%</small></span></div><button className="secondary-button full" onClick={onAdjustGoal}>调整目标</button></article>
      <article className="card plan-table-card"><div className="plan-tabs"><button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>计划总览</button><button className={tab === "knowledge" ? "active" : ""} onClick={() => setTab("knowledge")}>知识点列表</button></div>{tab === "overview" ? <><div className="plan-table-head"><span>任务</span><span>状态</span><span>预计用时</span><span>推荐理由</span></div><div className="plan-table">{tasks.map((task) => <button className="plan-row plan-row-button" key={task.id} onClick={() => onOpenTask(task)}><div className="plan-task"><span className={`timeline-dot ${task.status}`} /><div><strong>{task.title}</strong><small>{task.type}</small></div></div><span className={`status-pill ${task.status}`}>{statusLabels[task.status]}</span><span className="duration">{task.minutes ? `${task.minutes} 分钟` : "—"}</span><span className="reason">{task.reason}</span></button>)}</div></> : <div className="knowledge-list">{tasks.map((task) => <button className="knowledge-list-item" key={task.id} onClick={() => onOpenTask(task)}><span className="task-status in_progress"><Icon name="target" size={13} /></span><div><strong>{task.title}</strong><small>{task.description}</small></div><Icon name="chevron-right" size={16} /></button>)}</div>}</article>
    </section>
    <section className="plan-bottom-grid"><article className="card advice-card"><div className="card-heading"><span>学习建议</span><Icon name="spark" size={18} /></div>{advice.map((item, index) => index === 0 ? <p key={item}>{item}</p> : <div key={item}>{item}</div>)}</article><article className="card resources-card"><div className="card-heading"><span>推荐资料</span><Icon name="file" size={18} /></div>{resources.map((source) => <button key={source.id} onClick={() => onOpenSource(source)}><Icon name={source.type === "教材" ? "book" : "file"} size={16} /><span>{source.type} · {source.title}</span><Icon name="arrow-up-right" size={14} /></button>)}</article></section>
  </div>;
}

function WeeklyPlanView({ plan, book, onOpenItem, isUnlocked, onRegenerate, busy }: { plan: WeeklyPlan; book: Book; onOpenItem: (item: WeeklyPlanItem, dayId: number, date: string) => void; isUnlocked: (itemId: number) => boolean; onRegenerate: () => void; busy: boolean }) {
  const allItems = plan.days.flatMap((day) => day.items);
  const completed = allItems.filter((item) => item.status === "completed").length;
  const dateLabel = (value: string) => {
    const parsed = new Date(`${value}T00:00:00`);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "short" });
  };
  const itemKind = (item: WeeklyPlanItem) => item.source === "review_due" || item.title.startsWith("学习前诊断") ? "每日诊断" : item.title.startsWith("阅读：") ? "教材阅读" : "知识点答题";
  const itemIcon = (item: WeeklyPlanItem): IconName => itemKind(item) === "教材阅读" ? "book" : "target";
  return <div className="page-stack weekly-plan-page">
    <PageHeader eyebrow="MySQL · BKT 自适应排程" title="七天学习计划" description={`${book.title} · ${plan.plan.window_start_date} 至 ${plan.plan.window_end_date} · 每天 ${plan.plan.daily_minutes} 分钟`} action={<button className="outline-button" disabled={busy} onClick={onRegenerate}>{busy ? "正在生成…" : "重新生成七天计划"}</button>} />
    <section className="weekly-plan-summary card"><div><span className="section-label">计划目标</span><strong>以每日诊断校准掌握度，优先完成目标差距较大的知识点。</strong></div><div><span>{completed}/{allItems.length}</span><small>已完成任务</small></div><div><span>v{plan.plan.adaptive_version}</span><small>计划版本</small></div></section>
    <section className="weekly-day-grid">{plan.days.map((day, index) => <article className="card weekly-day-card" key={day.id}><header><div><span className="section-label">DAY {index + 1}</span><h2>{dateLabel(day.expected_date)}</h2></div><span className="status-pill blue">{day.items.length} 项</span></header><p className="weekly-day-reason">{day.adaptive_reason}</p><div className="weekly-item-list">{day.items.map((item) => { const locked = item.status !== "completed" && !isUnlocked(item.id); return <button className={`weekly-item ${locked ? "locked" : ""}`} key={item.id} disabled={locked} onClick={() => onOpenItem(item, day.id, day.expected_date)}><span className={`weekly-item-icon ${itemKind(item) === "教材阅读" ? "reading" : "question"}`}><Icon name={itemIcon(item)} size={16} /></span><span className="weekly-item-copy"><strong>{item.title}</strong><small>{itemKind(item)} · {item.status === "completed" ? "已完成" : locked ? "请先完成上一个任务" : "可开始"}</small></span><Icon name={locked ? "lock" : "chevron-right"} size={16} /></button>; })}</div></article>)}</section>
  </div>;
}

function ReadingMaterialDialog({ materials }: { materials: ReadingMaterials }) {
  return <article className="integrated-reading"><div className="integrated-reading-content">{materials.integrated_content}</div></article>;
}

function LegacyPlanView({ book, goal, goalLevel, tasks, tab, setTab, onOpenTask, onAdjustGoal, onOpenSource }: { book: Book; goal: string; goalLevel: string; tasks: LearningTask[]; tab: "overview" | "knowledge"; setTab: (tab: "overview" | "knowledge") => void; onOpenTask: (task: LearningTask) => void; onAdjustGoal: () => void; onOpenSource: (source: Source) => void }) {
  const completed = tasks.filter((task) => task.status === "completed").length;
  return <div className="page-stack"><PageHeader eyebrow="学习闭环 · 目标到任务" title="学习计划" description={`${book.title} · 系统会根据目标、诊断结果、用户校准和时间约束排列任务。`} action={<button className="outline-button" onClick={onAdjustGoal}>调整目标</button>} /><section className="plan-layout"><article className="card plan-summary"><span className="section-label">计划目标</span><h2>{goal}</h2><p>{goalLevel}</p><div className="ring-progress small"><span>{Math.round((completed / tasks.length) * 100)}<small>%</small></span></div><button className="secondary-button full" onClick={onAdjustGoal}>调整目标</button></article><article className="card plan-table-card"><div className="plan-tabs"><button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>计划总览</button><button className={tab === "knowledge" ? "active" : ""} onClick={() => setTab("knowledge")}>知识点列表</button></div>{tab === "overview" ? <><div className="plan-table-head"><span>任务</span><span>状态</span><span>预计用时</span><span>推荐理由</span></div><div className="plan-table">{tasks.map((task) => <button className="plan-row plan-row-button" key={task.id} onClick={() => onOpenTask(task)}><div className="plan-task"><span className={`timeline-dot ${task.status}`} /><div><strong>{task.title}</strong><small>{task.type}</small></div></div><span className={`status-pill ${task.status}`}>{statusLabels[task.status]}</span><span className="duration">{task.minutes ? `${task.minutes} 分钟` : "—"}</span><span className="reason">{task.reason}</span></button>)}</div></> : <div className="knowledge-list">{tasks.map((task) => <button className="knowledge-list-item" key={task.id} onClick={() => onOpenTask(task)}><span className="task-status in_progress"><Icon name="target" size={13} /></span><div><strong>{task.title}</strong><small>{task.description}</small></div><Icon name="chevron-right" size={16} /></button>)}</div>}</article></section><section className="plan-bottom-grid"><article className="card advice-card"><div className="card-heading"><span>学习建议</span><Icon name="spark" size={18} /></div><p>今天建议先完成{tasks.find((task) => task.status === "in_progress")?.title ?? tasks[0].title}，再进行一次短复测。</p><ul><li>保持连续学习，减少间隔过长</li><li>完成后进行 1 次短复测</li></ul></article><article className="card resources-card"><div className="card-heading"><span>推荐资料</span><Icon name="file" size={18} /></div><button onClick={() => onOpenSource({ id: "plan-book", type: "教材", title: `${book.shortTitle} · 重点章节`, location: "第 3 章", excerpt: `这份资料用于支持“${goal}”的学习目标。` })}><Icon name="book" size={16} /><span>教材 · 重点章节</span><Icon name="arrow-up-right" size={14} /></button><button onClick={() => onOpenSource({ id: "plan-note", type: "讲义", title: `${book.shortTitle} · 复习讲义`, location: "第 2 节", excerpt: "建议在完成练习后回看这份讲义，确认关键概念之间的关系。" })}><Icon name="file" size={16} /><span>讲义 · 复习重点</span><Icon name="arrow-up-right" size={14} /></button></article></section></div>;
}

function RecordsView({ records, total, page, pageSize, loading, filter, setFilter, onPageChange, onOpenRecord, onReview }: { records: RecordItem[]; total: number; page: number; pageSize: number; loading: boolean; filter: "all" | RecordItem["category"]; setFilter: (filter: "all" | RecordItem["category"]) => void; onPageChange: (page: number) => void; onOpenRecord: (record: RecordItem) => void; onReview: () => void }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  return <div className="page-stack"><PageHeader eyebrow="学习事件 · 可追溯" title="学习记录" description="查看人物画像、资料问答、能力诊断和学习任务活动。" action={<label className="filter-select"><Icon name="filter" size={15} /><select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)} aria-label="筛选学习记录"><option value="all">全部记录</option><option value="profile">人物画像</option><option value="task">学习任务</option><option value="diagnostic">能力诊断</option><option value="qa">资料问答</option></select></label>} /><section className="records-layout"><article className="card record-timeline"><div className="card-heading"><span>最近活动</span><span className="completion">{loading ? "正在加载" : `共 ${total} 个结果`}</span></div>{loading ? <EmptyState text="正在加载学习记录" /> : records.length === 0 ? <EmptyState text="暂时没有符合条件的记录" /> : records.map((item) => <div className="record-item" key={item.id}><div className={`record-icon ${item.tone}`}><Icon name={item.icon} size={16} /></div><div className="record-copy"><strong>{item.title}</strong><p>{item.description}</p><span>{item.time}</span></div><button className="icon-button" onClick={() => onOpenRecord(item)} aria-label="查看记录详情"><Icon name="chevron-right" size={17} /></button></div>)}{total > pageSize && <div className="record-pagination" aria-label="学习记录分页">{Array.from({ length: pageCount }, (_, index) => index + 1).map((pageNumber) => <button key={pageNumber} className={pageNumber === page ? "active" : ""} onClick={() => onPageChange(pageNumber)} disabled={loading}>{pageNumber}</button>)}</div>}</article>{records.length > 0 && <article className="card review-card"><div className="card-heading"><span>待复测</span><span className="status-pill warning">后端返回后显示</span></div><p>完成诊断后，系统会根据能力状态返回复测安排。</p><div className="review-item"><div><strong>开始复测</strong><span>重新检查当前知识点掌握情况</span></div><button className="secondary-button" onClick={onReview}>去复测</button></div></article>}</section></div>;
}

function QaView({ book, sources, messages, value, busy, error, onChange, onAsk, onNew, onOpenSource, onAddPlan }: { book: Book; sources: Source[]; messages: QaMessage[]; value: string; busy: boolean; error: string | null; onChange: (value: string) => void; onAsk: () => void; onNew: () => void; onOpenSource: (source: Source) => void; onAddPlan: () => void }) {
  const sourceBookTitle = (source: Source) => books.find((item) => item.id === source.bookId)?.title ?? book.title;
  const uniqueSources = mergeSourcesByChapter(sources);
  return <div className="page-stack"><PageHeader eyebrow="资料驱动 · 保留引用" title="资料问答" description="围绕当前学习内容和学习目标提问，回答会保留资料出处。" action={<button className="outline-button" onClick={onNew}>新建对话 <Icon name="plus" size={15} /></button>} /><section className="qa-layout"><article className="card conversation-card"><div className="conversation-head"><div><span className="section-label">当前范围</span><strong>{book.title} · {book.subtitle}</strong></div><span className="status-pill blue">已绑定知识点</span></div><div className="message-list">{messages.map((message, index) => <div className={`message ${message.role}`} key={`${message.role}-${index}`}><span className="message-avatar">{message.role === "assistant" ? "✦" : "我"}</span><div><p>{message.text}</p>{message.role === "assistant" && <div className="citation-row">{mergeSourcesByChapter(message.citations ?? sources).map((source) => <button key={sourceChapterKey(source)} onClick={() => onOpenSource(source)}><Icon name="file" size={14} /><span><strong>{sourceBookTitle(source)} · {source.contentUnitId || source.title}</strong><small>{source.location}</small></span><Icon name="chevron-right" size={14} /></button>)}</div>}</div></div>)}{busy && <div className="message assistant"><span className="message-avatar">✦</span><div className="typing-state">正在查找相关资料…</div></div>}{error && <div className="inline-error" role="alert"><Icon name="info" size={16} /><span>{error}</span><button onClick={onAsk}>重新发送</button></div>}</div><div className="chat-composer"><textarea value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onAsk(); } }} placeholder="继续提问（Shift + Enter 换行）" rows={2} /><button className="send-button" onClick={onAsk} disabled={busy} aria-label="发送问题"><Icon name="send" size={17} /></button></div><div className="suggestion-row"><button onClick={() => onChange("这个概念如何举例？")}>这个概念如何举例？</button><button onClick={() => onChange("需要哪些前置知识？")}>需要哪些前置知识？</button></div></article><aside className="card source-card"><div className="card-heading"><span>来源详情</span><Icon name="info" size={17} /></div>{uniqueSources.length === 0 ? <div className="source-empty">提问后显示检索到的资料来源</div> : uniqueSources.map((source) => <button className="source-block" key={sourceChapterKey(source)} onClick={() => onOpenSource(source)}><Icon name="file" size={15} /><strong>{sourceBookTitle(source)} · {source.contentUnitId || source.title}</strong></button>)}{uniqueSources.length > 0 && <button className="secondary-button full" onClick={onAddPlan}>加入学习计划 <Icon name="plus" size={15} /></button>}</aside></section></div>;
function QaView({ book, sources, messages, value, busy, error, answerMode, hasActiveLearningTask, onAnswerModeChange, onFinishSocraticTask, onChange, onAsk, onNew, onOpenSource, onAddPlan, onAskGeneral, relatedKnowledgePointIds }: { book: Book; sources: Source[]; messages: QaMessage[]; value: string; busy: boolean; error: string | null; answerMode: QaAnswerMode; hasActiveLearningTask: boolean; onAnswerModeChange: (mode: QaAnswerMode) => void; onFinishSocraticTask: () => void; onChange: (value: string) => void; onAsk: () => void; onNew: () => void; onOpenSource: (source: Source) => void; onAddPlan: () => void; onAskGeneral: (question: string) => void; relatedKnowledgePointIds: string[] }) {
  const sourceBookTitle = (source: Source) => books.find((item) => item.id === source.bookId)?.title ?? book.title;
  const uniqueSources = mergeSourcesByChapter(sources);
  // 清空会写入上下文重置标记；回答生成期间禁止清空，避免在途回答越过重置边界。
  return <div className="page-stack"><PageHeader eyebrow="资料驱动 · 保留引用" title="资料问答" description="围绕当前学习内容和学习目标提问，回答会保留资料出处。" action={<button className="outline-button" onClick={onNew} title="清空当前对话，重新开始一轮提问">清空对话 <Icon name="trash" size={15} /></button>} /><section className="qa-layout"><article className="card conversation-card"><div className="conversation-head"><div><span className="section-label">当前范围</span><strong>{book.title} · {book.subtitle}</strong></div><span className="status-pill blue">已绑定知识点</span></div><div className="qa-mode-bar"><div className="qa-mode-switch" aria-label="回答方式"><button className={answerMode === "direct" ? "active" : ""} onClick={() => onAnswerModeChange("direct")} disabled={busy}>直接回答</button><button className={answerMode === "socratic" ? "active" : ""} onClick={() => onAnswerModeChange("socratic")} disabled={busy}>引导作答</button></div><span>{answerMode === "socratic" ? "每轮只给一个问题或提示，不直接泄露完整答案" : "直接根据教材给出有出处的回答"}</span>{answerMode === "socratic" && hasActiveLearningTask && <button className="qa-finish-task" onClick={onFinishSocraticTask} disabled={busy}>结束本轮引导</button>}</div><div className="message-list">{messages.map((message, index) => <div className={`message ${message.role}`} key={`${message.role}-${index}`}><span className="message-avatar">{message.role === "assistant" ? "✦" : "我"}</span><div>{message.fromGeneralModel && <div className="general-model-tag"><Icon name="alert" size={13} />此回答来自通用模型，未经教材验证，不计入学习记录</div>}{message.role === "assistant" && message.answerMode === "socratic" && <div className="socratic-tag">引导作答{message.socraticCompleted ? " · 已完成" : ""}</div>}<p className={message.fromGeneralModel ? "general-model-answer" : undefined}>{message.text}</p>{message.role === "assistant" && message.refused && message.answerMode !== "socratic" && <div className="qa-fallback"><span>资料里没有找到能支持这个问题的依据。</span><button type="button" onClick={() => onAskGeneral(message.question ?? "")} disabled={!message.question}>用通用模型回答（无教材引用）</button><InlineResources knowledgePointIds={relatedKnowledgePointIds} title="或者看看这些资料" /></div>}{message.role === "assistant" && !message.refused && !message.fromGeneralModel && <div className="citation-row">{mergeSourcesByChapter(message.citations ?? sources).map((source) => <button key={sourceChapterKey(source)} onClick={() => onOpenSource(source)}><Icon name="file" size={14} /><span><strong>{sourceBookTitle(source)} · {source.contentUnitId || source.title}</strong><small>{source.location}</small></span><Icon name="chevron-right" size={14} /></button>)}</div>}</div></div>)}{busy && <div className="message assistant"><span className="message-avatar">✦</span><div className="typing-state">{answerMode === "socratic" ? "正在判断下一步引导…" : "正在查找相关资料…"}</div></div>}{error && <div className="inline-error" role="alert"><Icon name="info" size={16} /><span>{error}</span><button onClick={onAsk}>重新发送</button></div>}</div><div className="chat-composer"><textarea value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onAsk(); } }} placeholder={answerMode === "socratic" ? (hasActiveLearningTask ? "回答导师的问题（Shift + Enter 换行）" : "输入一道题，开始引导作答") : "继续提问（Shift + Enter 换行）"} rows={2} /><button className="send-button" onClick={onAsk} disabled={busy} aria-label="发送问题"><Icon name="send" size={17} /></button></div><div className="suggestion-row">{answerMode === "socratic" ? <><button onClick={() => onChange("我不太确定，请给我一个提示")}>给我一个提示</button><button onClick={() => onChange("我认为可以先从核心概念开始分析")}>我先说说思路</button></> : <><button onClick={() => onChange("这个概念如何举例？")}>这个概念如何举例？</button><button onClick={() => onChange("需要哪些前置知识？")}>需要哪些前置知识？</button></>}</div></article><aside className="card source-card"><div className="card-heading"><span>来源详情</span><Icon name="info" size={17} /></div>{uniqueSources.length === 0 ? <div className="source-empty">提问后显示检索到的资料来源</div> : uniqueSources.map((source) => <button className="source-block" key={sourceChapterKey(source)} onClick={() => onOpenSource(source)}><Icon name="file" size={15} /><strong>{sourceBookTitle(source)} · {source.contentUnitId || source.title}</strong></button>)}{uniqueSources.length > 0 && <button className="secondary-button full" onClick={onAddPlan}>加入学习计划 <Icon name="plus" size={15} /></button>}</aside></section></div>;
}

function TaskRow({ task, onOpen }: { task: LearningTask; onOpen: () => void }) {
  return <button className="task-row task-row-button" onClick={onOpen}><span className={`task-status ${task.status}`}>{task.status === "completed" ? <Icon name="check" size={13} /> : task.status === "in_progress" ? <i /> : <span />}</span><div><strong>{task.title}</strong><small>{task.type} · 预计 {task.expectedCompletionDate ?? "今天"} 完成</small></div><span className="task-duration">{task.minutes} 分钟</span><span className="task-state">{statusLabels[task.status]}</span></button>;
}

function MaterialPlanEditor({ onSave }: { onSave: (payload: Omit<import("./services/api").MaterialLearningPlanPayload, "bookId" | "resources">) => Promise<void> }) {
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [description, setDescription] = useState("");
  const [minutes, setMinutes] = useState(20);
  const [expectedCompletionDate, setExpectedCompletionDate] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!title.trim() || !goal.trim()) return;
    setBusy(true);
    try {
      await onSave({ title: title.trim(), goal: goal.trim(), description: description.trim(), minutes, expectedCompletionDate });
    } finally {
      setBusy(false);
    }
  };

  return <div className="goal-editor"><label className="control-field"><span>计划名称</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：复习过拟合与模型评估" /></label><label className="control-field"><span>学习目标</span><input value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="例如：能够判断模型是否过拟合" /></label><label className="control-field"><span>任务说明</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="补充这次学习任务的具体要求" rows={3} /></label><div className="form-grid"><label className="control-field"><span>预计用时（分钟）</span><input type="number" min={5} max={240} value={minutes} onChange={(event) => setMinutes(Number(event.target.value))} /></label><label className="control-field"><span>预计完成日期</span><input type="date" value={expectedCompletionDate} onChange={(event) => setExpectedCompletionDate(event.target.value)} /></label></div><button className="primary-button full" disabled={busy || !title.trim() || !goal.trim()} onClick={() => void submit()}>{busy ? "正在创建…" : "加入学习计划"}</button></div>;
}

function GoalEditor({ initialValue, onSave }: { initialValue: string; onSave: (value: string) => void }) {
  const [value, setValue] = useState(initialValue);
  return <div className="goal-editor"><label className="control-field"><span>目标水平</span><select value={value} onChange={(event) => setValue(event.target.value)}><option>了解核心概念</option><option>能够独立完成基础练习</option><option>能够迁移到项目实践</option></select></label><button className="primary-button full" onClick={() => onSave(value)}>保存目标</button></div>;
}

function EmptyState({ text }: { text: string }) { return <div className="empty-state"><Icon name="file" size={21} /><strong>{text}</strong><span>调整筛选条件后可以继续查看。</span></div>; }

function Modal({ modal, onClose }: { modal: ModalState; onClose: () => void }) {
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="modal-header"><div><span className="eyebrow">操作详情</span><h2 id="modal-title">{modal.title}</h2>{modal.subtitle && <p>{modal.subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label="关闭"><Icon name="close" size={18} /></button></div><div className="modal-content">{modal.content}</div><div className="modal-actions">{modal.secondary && <button className="outline-button" onClick={modal.secondary.onClick}>{modal.secondary.label}</button>}{modal.primary && <button className="primary-button" disabled={modal.primary.disabled} onClick={modal.primary.onClick}>{modal.primary.label}</button>}</div></section></div>;
}

export { App };
