import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Icon, type IconName } from "./components/Icon";
import { LearnerProfileView } from "./components/LearnerProfileView";
import { AuthView } from "./components/AuthView";
import { GoalsSetupView } from "./components/GoalsSetupView";
import { SettingsView } from "./components/SettingsView";
import { InlineResources, LearningResourcesView } from "./components/LearningResources";
import { HelpCenterView } from "./components/HelpCenter";
import { CommunityView } from "./components/CommunityView";
import { MotivationView } from "./components/MotivationView";
import { PracticeView } from "./components/PracticeView";
import { auth, getSession, type AuthUser } from "./services/session";
import { api, practiceApi, USE_REAL_API, type ApiError, type BookCatalogItem, type DiagnosticResult, type LearningActivity, type LearningPlanResult, type PlanTimeBudget, type PracticeAchievement, type QaAnswerMode, type QaAttachment, type TodayLearningResponse, type DailyLearningPlan, type LearningRecordSummary } from "./services/api";
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
  attachments?: Array<Pick<QaAttachment, "fileName" | "fileType" | "fileUrl">>;
};
type QaAttachmentDraft = { file: File; previewUrl: string };
type SavedDiagnosticSession = {
  diagnosticId: string;
  questions: DiagnosticQuestion[];
  index: number;
  answers: Record<string, string>;
  skippedQuestions: string[];
  practiceTask: LearningTask | null;
};
type ModalState = {
  title: string;
  subtitle?: string;
  content: ReactNode;
  primary?: { label: string; onClick: () => void; disabled?: boolean };
  secondary?: { label: string; onClick: () => void };
};

const sourceChapterKey = (source: Source) => [
  source.bookId ?? "",
  source.chapterId ?? source.contentUnitId ?? source.location ?? source.title,
].join("::");

const mergeSourcesByChapter = (sources: Source[]) =>
  Array.from(new Map(sources.map((source) => [sourceChapterKey(source), source])).values());

const localDateInputValue = (date = new Date()) => {
  const timezoneOffsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - timezoneOffsetMs).toISOString().slice(0, 10);
};

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
  { key: "plan", label: "学习计划", icon: "calendar" },
  { key: "records", label: "学习记录", icon: "chart" },
  { key: "qa", label: "资料问答", icon: "chat" },
  { key: "resources", label: "学习资源", icon: "spark" },
  { key: "community", label: "学习社区", icon: "users" },
  { key: "motivation", label: "荣誉排行", icon: "trophy" },
];

const statusLabels: Record<TaskStatus, string> = {
  completed: "已完成",
  in_progress: "进行中",
  todo: "待开始",
  review_due: "待复测",
  skipped: "已跳过",
  rescheduled: "已改期",
};

const errorMessage = (error: unknown) => {
  const apiError = error as ApiError;
  const details = apiError?.details as { previous_title?: string; previous_item_id?: number } | undefined;
  if (apiError?.message === "complete the previous learning-plan task first") {
    return details?.previous_title
      ? `请先完成上一项任务“${details.previous_title}”，再开始当天诊断。`
      : "请先完成上一项学习任务，再开始当天诊断。";
  }
  if (apiError?.message === "learningPlanItemId does not belong to learningPlanDayId") {
    return "当前诊断任务与学习计划不匹配，请刷新学习计划后重试。";
  }
  return apiError?.message ?? "操作失败，请稍后重试。";
};

const goalLevelOptions = [
  "能够复述核心概念",
  "能够独立完成基础练习",
  "能够解决进阶应用问题",
  "能够指导他人 / 应对面试",
] as const;

/** 记录该用户是否已完成「选书与目标」，决定登录后是否先进入引导流程。 */
const goalStorageKey = (userId: string) => `study-companion.goal.${userId}`;
const diagnosticStorageKey = (userId: string, bookId: BookId) => `study-companion.diagnostic.${userId}.${bookId}`;

function readSavedGoal(userId: string): { bookId: string; targetLevel: string } | null {
  try {
    const raw = window.localStorage.getItem(goalStorageKey(userId));
    return raw ? (JSON.parse(raw) as { bookId: string; targetLevel: string }) : null;
  } catch {
    return null;
  }
}

function readSavedDiagnostic(userId: string, bookId: BookId): SavedDiagnosticSession | null {
  try {
    const raw = window.localStorage.getItem(diagnosticStorageKey(userId, bookId));
    if (!raw) return null;
    const saved = JSON.parse(raw) as SavedDiagnosticSession;
    // 旧版 Demo 页面把模拟题和 demo-* ID 写入了本地缓存。该 ID 从未
    // 存在于真实后端，恢复它会让每一次提交都变成 404。
    if (!saved.diagnosticId || saved.diagnosticId.startsWith("demo-") || !Array.isArray(saved.questions) || saved.questions.length === 0) {
      window.localStorage.removeItem(diagnosticStorageKey(userId, bookId));
      return null;
    }
    return saved;
  } catch {
    return null;
  }
}

function clearSavedDiagnostic(userId: string | undefined, bookId: BookId) {
  if (!userId) return;
  try {
    window.localStorage.removeItem(diagnosticStorageKey(userId, bookId));
  } catch {
    // 本地存储不可用时不影响诊断流程。
  }
}

function App() {
  const [user, setUser] = useState<AuthUser | null>(() => getSession()?.user ?? null);
  const [bookCatalog, setBookCatalog] = useState<BookCatalogItem[]>([]);
  const [knowledgePointNames, setKnowledgePointNames] = useState<Record<string, string>>({});
  const [activeNav, setActiveNav] = useState<NavKey>("today");
  const pageContentRef = useRef<HTMLDivElement>(null);
  const [bookId, setBookId] = useState<BookId>(books[0].id);
  const [toast, setToast] = useState<Toast>(null);
  const [modal, setModal] = useState<ModalState | null>(null);
  // 全局队列负责在学习任务页面和独立答题页面展示新勋章。
  const [achievementNotices, setAchievementNotices] = useState<PracticeAchievement[]>([]);
  const [taskStates, setTaskStates] = useState<Record<string, TaskStatus>>({});
  const [generatedPlan, setGeneratedPlan] = useState<LearningPlanResult | null>(null);
  const [planRegenerating, setPlanRegenerating] = useState(false);
  const [todayLearning, setTodayLearning] = useState<TodayLearningResponse | null>(null);
  const [planTab, setPlanTab] = useState<"overview" | "knowledge">("overview");
  const [goalLevel, setGoalLevel] = useState("能够独立完成基础练习");

  const refreshAchievementNotices = async () => {
    // 任务完成是解锁条件变化的时机，因此这里才强制刷新完整进度。
    const result = await practiceApi.achievementProgress(true);
    setAchievementNotices((current) => {
      const merged = [...current];
      // 同一个勋章在确认前可能被多次查询到，因此按数据库主键去重。
      result.newlyUnlocked.forEach((item) => { if (!merged.some((existing) => existing.id === item.id)) merged.push(item); });
      return merged;
    });
  };

  const closeAchievementNotice = () => {
    const achievement = achievementNotices[0];
    if (!achievement) return;
    void practiceApi.acknowledgeAchievement(achievement.id).catch(() => undefined);
    setAchievementNotices((items) => items.slice(1));
  };

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
  const [diagnosticError, setDiagnosticError] = useState<string | null>(null);
  const [diagnosticId, setDiagnosticId] = useState("");
  const [practiceTask, setPracticeTask] = useState<LearningTask | null>(null);
  const [diagnosticResult, setDiagnosticResult] = useState<DiagnosticResult | null>(null);
  const [calibration, setCalibration] = useState<Calibration | null>(null);
  const [calibrationReason, setCalibrationReason] = useState("");

  // 诊断题逐题提交到后端的同时，在本地保存会话快照；刷新或暂时离开后可从当前题继续。
  useEffect(() => {
    const hasProgress = diagnosticIndex > 0 || Object.keys(diagnosticAnswers).length > 0 || skippedQuestions.length > 0;
    if (!user || diagnosticBusy || diagnosticStage !== "question" || diagnosticQuestions.length === 0 || (activeNav !== "diagnostic" && !hasProgress)) return;
    try {
      const snapshot: SavedDiagnosticSession = {
        diagnosticId,
        questions: diagnosticQuestions,
        index: Math.min(Math.max(0, diagnosticIndex), diagnosticQuestions.length - 1),
        answers: diagnosticAnswers,
        skippedQuestions,
        practiceTask,
      };
      window.localStorage.setItem(diagnosticStorageKey(user.userId, bookId), JSON.stringify(snapshot));
    } catch {
      // 本地存储不可用时仍可在当前页面继续答题。
    }
  }, [activeNav, bookId, diagnosticAnswers, diagnosticBusy, diagnosticId, diagnosticIndex, diagnosticQuestions, diagnosticStage, practiceTask, skippedQuestions, user]);

  const [recordFilter, setRecordFilter] = useState<"all" | RecordItem["category"]>("all");
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordPage, setRecordPage] = useState(1);
  const [recordTotal, setRecordTotal] = useState(0);
  const [recordSummary, setRecordSummary] = useState<LearningRecordSummary | null>(null);
  const recordPageSize = 10;
  const [recordStartDate, setRecordStartDate] = useState(() => localDateInputValue());
  const [recordEndDate, setRecordEndDate] = useState(() => localDateInputValue());
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
  const [qaAttachment, setQaAttachment] = useState<QaAttachmentDraft | null>(null);
  // 仅当用户从一道诊断题进入资料问答时保留返回入口；普通资料问答不显示它。
  const [qaReturnToDiagnostic, setQaReturnToDiagnostic] = useState(false);

  // 优先使用目录接口返回的书籍信息，目录未加载时回退本地定义。
  const currentBook = useMemo<Book>(() => {
    const fromCatalog = bookCatalog.find((book) => book.id === bookId);
    if (fromCatalog) return { id: fromCatalog.id, title: fromCatalog.title, shortTitle: fromCatalog.shortTitle, subtitle: fromCatalog.subtitle };
    return books.find((book) => book.id === bookId) ?? books[0];
  }, [bookCatalog, bookId]);
  const bookOptions = bookCatalog.length > 0 ? bookCatalog : books;
  const content = useMemo(() => getBookContent(bookId), [bookId]);
  const currentTasks = useMemo(
    // 本地 mock 才允许用演示任务兜底。真实服务没有活动计划时继续
    // 展示这些无数据库 ID 的任务，会让“完成”看似成功却无法同步。
    () => (generatedPlan?.tasks ?? (USE_REAL_API ? [] : content.planTasks)).map((task) => ({ ...task, status: taskStates[task.id] ?? task.status })),
    [content, generatedPlan, taskStates],
  );
  // 今日学习的任务状态 = 后端返回值叠加本地乐观更新，避免点击完成后界面不动。
  const todayDashboard = useMemo<TodayLearningResponse | null>(() => {
    if (!todayLearning) return null;
    return { ...todayLearning, tasks: todayLearning.tasks.map((task) => ({ ...task, status: taskStates[task.id] ?? task.status })) };
  }, [todayLearning, taskStates]);
  const currentQuestion = diagnosticQuestions[diagnosticIndex] ?? diagnosticQuestions[0];

  const loadRecords = async () => {
    setRecordsLoading(true);
    try {
      const result = await api.getLearningRecords({ category: recordFilter, startDate: recordStartDate, endDate: recordEndDate, page: recordPage, pageSize: recordPageSize });
      setRecords(result.records.map(toRecordItem));
      setRecordTotal(result.total);
      setRecordSummary(result.summary ?? null);
    } catch (error) {
      setRecords([]);
      setRecordSummary(null);
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

  const initializeQaContext = async (nextBookId: BookId, resetContext = false): Promise<boolean> => {
    setQaContextBusy(true);
    setQaContextToken(null);
    setQaMessages([]);
    setQaSources([]);
    setQaError(null);
    setQaAttachment(null);
    try {
      const context = await api.initializeQaContext(nextBookId, resetContext);
      setQaContextToken(context.conversationId);
      setQaAnswerMode(context.answerMode ?? "direct");
      setQaLearningTaskId(context.learningTaskId ?? null);
      if (resetContext) showToast("已清空对话", "之后的回答不会再使用此前的问答内容。");
      return true;
    } catch (error) {
      setQaError(errorMessage(error));
      return false;
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
    // 两种回答模式拥有不同的会话语义：直接回答允许基于资料连续追问，
    // 引导作答则会维护独立的 Socratic 状态。切换时必须创建新会话，
    // 避免旧模式的消息、引导任务和上下文泄漏到新模式。
    const initialized = await initializeQaContext(bookId, true);
    if (!initialized) return;
    setQaAnswerMode(mode);
    setQaLearningTaskId(null);
    setQaError(null);
    showToast("已切换回答模式", "旧对话已清空，当前模式将从新的会话开始。 ");
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
    if (!user) return;
    void initializeQaContext(bookId);
  }, [user?.userId, bookId]);

  useEffect(() => {
    if (!user) return;
    void loadRecords();
  }, [user?.userId, bookId, recordFilter, recordStartDate, recordEndDate, recordPage]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    setGeneratedPlan(null);
    void api.getLearningPlan(bookId).then((result) => {
      if (active && result.exists) setGeneratedPlan(result.plan);
    }).catch(() => {
      // 没有已保存计划时，继续展示空计划状态。
    });
    return () => { active = false; };
  }, [user?.userId, bookId]);

  // 拉取今日学习聚合数据；任务状态变化后需要重新调用，否则页面停留在旧状态。
  const reloadTodayLearning = async (targetBookId: BookId = bookId) => {
    try {
      const result = await api.getTodayLearning(targetBookId);
      setTodayLearning(result);
      // 只清除后端已经追上的那些本地状态：
      // 后端持久化成功 -> 覆盖层自动消失；后端尚未落库 -> 保留用户刚做的操作，界面不会回退。
      setTaskStates((states) => {
        const serverStatus = new Map(result.tasks.map((task) => [task.id, task.status]));
        return Object.fromEntries(Object.entries(states).filter(([id, status]) => serverStatus.get(id) !== status));
      });
    } catch {
      // 保留当前展示内容，避免刷新失败时页面变空。
    }
  };

  useEffect(() => {
    if (!user) return;
    let active = true;
    setTodayLearning(null);
    void api.getTodayLearning(bookId).then((result) => {
      if (active) setTodayLearning(result);
    }).catch(() => {
      if (active) setTodayLearning(null);
    });
    return () => { active = false; };
  }, [user?.userId, bookId]);

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

  const changeRecordDateRange = (startDate: string, endDate: string) => {
    setRecordPage(1);
    setRecordStartDate(startDate);
    setRecordEndDate(endDate < startDate ? startDate : endDate);
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
    setDiagnosticId("");
    setDiagnosticResult(null);
    setCalibration(null);
    setCalibrationReason("");
    setQaReturnToDiagnostic(false);
    void initializeQaContext(nextBookId);
    showToast("已切换学习内容", `${getBookContent(nextBookId).goal}的页面内容已更新。`);
  };

  const goTo = (key: NavKey) => {
    if (key === "diagnostic") {
      const todayDiagnostic = currentTasks.find((task) => task.type === "能力诊断" && (task.status ?? "todo") !== "completed");
      void startDiagnostic(todayDiagnostic);
      return;
    }
    if (key === "qa") setQaReturnToDiagnostic(false);
    setActiveNav(key);
  };

  const startDiagnostic = async (task?: LearningTask) => {
    const savedSession = user ? readSavedDiagnostic(user.userId, bookId) : null;
    if (savedSession) {
      setActiveNav("diagnostic");
      setDiagnosticStage("question");
      setDiagnosticId(savedSession.diagnosticId);
      setDiagnosticQuestions(savedSession.questions);
      setDiagnosticIndex(Math.min(Math.max(0, savedSession.index), savedSession.questions.length - 1));
      setDiagnosticAnswers(savedSession.answers);
      setSkippedQuestions(savedSession.skippedQuestions);
      setDiagnosticPaused(false);
      setDiagnosticError(null);
      setPracticeTask(savedSession.practiceTask);
      showToast("已恢复答题", `已回到第 ${Math.min(Math.max(0, savedSession.index), savedSession.questions.length - 1) + 1} 题，之前的答案已保留。`);
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    let boundTask = task ?? currentTasks.find((candidate) => candidate.type === "能力诊断" && candidate.expectedCompletionDate?.startsWith(today) && (taskStates[candidate.id] ?? candidate.status) !== "completed") ?? currentTasks.find((candidate) => candidate.type === "能力诊断" && (taskStates[candidate.id] ?? candidate.status) !== "completed");
    if (!boundTask) {
      try {
        const latest = await api.getLearningPlan(bookId);
        const todayPlan = latest.plan?.dailyPlans?.find((day) => day.date.startsWith(today));
        boundTask = todayPlan?.tasks.find((candidate) => candidate.type === "能力诊断" && candidate.status !== "completed");
      } catch {
        // The normal error handling below reports unavailable diagnostics.
      }
    }
    setActiveNav("diagnostic");
    setDiagnosticStage("question");
    setDiagnosticIndex(0);
    setDiagnosticAnswers({});
    setDiagnosticError(null);
    // 清掉初始化/上一轮题目，避免后端加载期间误显示默认题目。
    setDiagnosticQuestions([]);
    setSkippedQuestions([]);
    setDiagnosticPaused(false);
    setDiagnosticBusy(true);
    const isPractice = Boolean(boundTask && boundTask.type !== "能力诊断");
    setPracticeTask(isPractice ? boundTask ?? null : null);
    try {
      const result = await api.startDiagnostic(bookId, content.goal, boundTask?.planDayId, boundTask?.id, isPractice ? "practice" : "diagnostic");
      setDiagnosticId(result.diagnosticId);
      setDiagnosticQuestions(result.questions);
      showToast("诊断已开始", `共 ${result.questions.length} 道题，答案会逐题保存。`);
    } catch (error) {
      setDiagnosticError(errorMessage(error));
      showToast("诊断启动失败", errorMessage(error));
    } finally {
      setDiagnosticBusy(false);
    }
  };

  const advanceDiagnostic = async (question: DiagnosticQuestion, answer?: string, skipped = false) => {
    // 热更新前遗留的 Demo 会话可能仍保存在当前 React 状态中。不要把
    // 模拟题答案发给真实 API；清理后立即创建后端会话。
    if (diagnosticId.startsWith("demo-")) {
      clearSavedDiagnostic(user?.userId, bookId);
      await startDiagnostic();
      showToast("已创建新的诊断", "旧版演示会话已清除，请在新题目中继续作答。 ");
      return;
    }
    setDiagnosticBusy(true);
    try {
      await api.submitDiagnosticAnswer(diagnosticId, { questionId: question.id, answer: answer ?? "", skipped });
      if (diagnosticIndex >= diagnosticQuestions.length - 1) {
        const result = await api.finishDiagnostic(diagnosticId);
        clearSavedDiagnostic(user?.userId, bookId);
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
    if (practiceTask) {
      setDiagnosticBusy(true);
      try {
        // 计划项状态是主事实，先写入 MySQL。学习记录写入失败不能让
        // 已完成的练习重新显示成未完成。
        if (/^\d+$/.test(practiceTask.id)) await api.completeLearningPlanItem(practiceTask.id);
        setTaskStates((states) => ({ ...states, [practiceTask.id]: "completed" }));
        let recordError: unknown = null;
        try {
          await api.writeLearningEvent({ taskId: practiceTask.id, taskTitle: practiceTask.title, eventType: "task_completed", status: "completed", bookId, durationSeconds: Math.round(practiceTask.minutes * 60), plannedMinutes: practiceTask.minutes });
        } catch (error) {
          recordError = error;
        }
        await loadRecords();
        await reloadTodayLearning();
        await api.getLearningPlan(bookId).then((result) => {
          if (result.exists && result.plan) setGeneratedPlan(result.plan);
        }).catch(() => undefined);
        setPracticeTask(null);
        setActiveNav("plan");
        showToast(recordError ? "练习已完成，记录待补写" : "练习已完成", recordError ? `计划状态已同步；学习记录暂未写入：${errorMessage(recordError)}` : "已同步更新学习计划和学习记录。 ");
      } catch (error) {
        showToast("练习完成失败", errorMessage(error));
      } finally {
        setDiagnosticBusy(false);
      }
      return;
    }
    if (!calibration) {
      showToast("请选择自我判断", "提交前请先选择与你最接近的能力水平。 ");
      return;
    }
    setDiagnosticBusy(true);
    try {
      await api.submitCalibration({ diagnosticId, level: calibration, reason: calibrationReason });
      await loadRecords();
      await reloadTodayLearning();
      await api.getLearningPlan(bookId).then((result) => {
        if (result.exists && result.plan) setGeneratedPlan(result.plan);
      }).catch(() => undefined);
      setActiveNav("plan");
      showToast("校准已提交", "诊断结果已用于更新掌握度，后续计划会据此动态调整。 ");
    } catch (error) {
      showToast("校准提交失败", errorMessage(error));
    } finally {
      setDiagnosticBusy(false);
    }
  };

  const ensureWeeklyPlan = async (profileBookId: BookId, force = false, regenerationReason = "", aimLevel?: number) => {
    if (force) setPlanRegenerating(true);
    try {
      const existing = await api.getLearningPlan(profileBookId);
      if (!force && existing.exists && existing.plan) {
        setGeneratedPlan(existing.plan);
        setActiveNav("plan");
        return;
      }
      const plan = await api.generateWeeklyPlan(profileBookId, regenerationReason, aimLevel);
      // 生成接口只返回本次新排的后续日期；必须回读已持久化的完整计划，
      // 否则历史已完成任务会被前端临时状态遮蔽，表现得像被删除。
      const refreshed = await api.getLearningPlan(profileBookId);
      setGeneratedPlan(refreshed.plan ?? plan);
      if (aimLevel !== undefined) setGoalLevel(goalLevelOptions[aimLevel]);
      await reloadTodayLearning(profileBookId);
      setActiveNav("plan");
      showToast(force ? "后续计划已更新" : "学习计划已生成", force ? "已完成任务保持不变，系统已按新的目标和建议重排后续任务。" : "已根据你的目标和学习画像安排未来 7 天任务；每日诊断会继续动态调整后续安排。");
    } catch (error) {
      showToast(force ? "重新生成失败" : "暂时无法生成计划", `请确认已保存学习目标和学习画像：${errorMessage(error)}`);
    } finally {
      if (force) setPlanRegenerating(false);
    }
  };

  const openPlanAdjustment = () => setModal({
    title: "调整并生成计划",
    subtitle: "可修改目标或补充调整建议；已完成任务不会被更改。",
    content: <RegeneratePlanForm initialGoalLevel={goalLevel} onConfirm={(level, reason) => { closeModal(); void ensureWeeklyPlan(bookId, true, reason, Math.max(0, goalLevelOptions.indexOf(level))); }} />,
    secondary: { label: "取消", onClick: closeModal },
  });

  const updateTask = async (task: LearningTask, actualMinutes?: number, forceComplete = false) => {
    const currentStatus = taskStates[task.id] ?? task.status;
    const nextStatus: TaskStatus = forceComplete || currentStatus === "completed" || currentStatus === "in_progress" ? "completed" : "in_progress";
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
    let completionRecordError: unknown = null;
    try {
      if (nextStatus === "in_progress" && /^\d+$/.test(task.id)) {
        await api.startLearningPlanItem(task.id);
      }
      if (nextStatus === "completed") {
        // 先更新计划项。此前若学习记录服务暂不可用，下面的记录请求会
        // 抛错并中断，导致 MySQL 中的计划项根本没有被标记完成。
        if (/^\d+$/.test(task.id)) {
          await api.completeLearningPlanItem(task.id);
        }
        try {
          await api.writeLearningEvent({
          taskId: task.id,
          taskTitle: task.title,
          eventType: "task_completed",
          status: nextStatus,
          bookId,
          durationSeconds: Math.round((actualMinutes ?? task.minutes) * 60),
          plannedMinutes: task.minutes,
          });
          void refreshAchievementNotices().catch(() => undefined);
        } catch (error) {
          completionRecordError = error;
        }
      }
      await loadRecords();
      await reloadTodayLearning();
      if (nextStatus === "completed") {
        // 后端会用这条新的「计划 vs 实际」样本重排剩下任务的日期，重新拉一次计划才看得到。
        await api.getLearningPlan(bookId)
          .then((result) => { if (result.exists) setGeneratedPlan(result.plan); })
          .catch(() => undefined);
      }
      showToast(
        nextStatus === "completed" && completionRecordError ? "任务已完成，记录待补写" : nextStatus === "completed" ? "任务已完成" : "任务已开始",
        nextStatus === "completed"
          ? completionRecordError ? `计划状态已同步；学习记录暂未写入：${errorMessage(completionRecordError)}` : "计划状态已同步，下一项学习任务已经准备好。"
          : "完成后可以继续更新学习进度。 ",
      );
    } catch (error) {
      setTaskStates((states) => ({
        ...states,
        [task.id]: currentStatus,
        ...(nextTask && previousNextStatus ? { [nextTask.id]: previousNextStatus } : {}),
      }));
      showToast("任务更新失败", errorMessage(error));
      // 学习事件可能已成功写入，即使计划项状态更新失败也刷新记录列表。
      await loadRecords();
    }
  };

  const startReadingTask = async (task: LearningTask) => {
    if ((taskStates[task.id] ?? task.status) !== "todo") return;
    setTaskStates((states) => ({ ...states, [task.id]: "in_progress" }));
    try {
      await api.writeLearningEvent({ taskId: task.id, taskTitle: task.title, eventType: "task_started", status: "in_progress", bookId, plannedMinutes: task.minutes });
      if (/^\d+$/.test(task.id)) await api.startLearningPlanItem(task.id);
    } catch (error) {
      setTaskStates((states) => ({ ...states, [task.id]: task.status }));
      showToast("阅读开始记录失败", errorMessage(error));
    }
  };

  const openTask = (task: LearningTask) => {
    const status = taskStates[task.id] ?? task.status;
    if (task.title.startsWith("阅读：")) {
      const openingStatus = taskStates[task.id] ?? task.status;
      if (openingStatus === "todo") void startReadingTask(task);
      setModal({
        title: task.title,
        subtitle: "教材与网络资料整合讲义 · 正在加载",
        content: <div className="task-detail"><p>正在定位教材章节并整合相关网络资料…</p></div>,
        secondary: { label: "关闭", onClick: closeModal },
      });
      void api.getReadingMaterials(bookId, task.title).then((reading) => {
        setModal({
          title: task.title,
          subtitle: reading.generated_by === "llm" ? "教材为主 · 已整合网络补充" : "教材内容 · 网络资料暂不可用时使用教材兜底",
      content: <div className="task-detail reading-detail"><div className="reading-content" style={{ whiteSpace: "pre-wrap" }}>{reading.integrated_content}</div>{reading.search_error && <p className="inline-hint">{reading.search_error}</p>}{reading.references.length > 0 && <div className="detail-grid"><span>内容来源</span><div>{reading.references.map((reference) => <p key={`${reference.title}-${reference.location}`}><strong>{reference.title}</strong><br /><small>{reference.location}</small></p>)}</div></div>}</div>,
          secondary: { label: "关闭", onClick: closeModal },
          primary: status === "completed" ? undefined : { label: "完成阅读", onClick: () => { closeModal(); void updateTask(task, undefined, true); } },
        });
      }).catch((error) => showToast("阅读内容加载失败", errorMessage(error)));
      return;
    }
    if (task.type === "编程实践" || task.title.startsWith("编程实践：")) {
      if (status === "todo") {
        setTaskStates((states) => ({ ...states, [task.id]: "in_progress" }));
        if (/^\d+$/.test(task.id)) void api.startLearningPlanItem(task.id).catch(() => undefined);
      }
      setModal({ title: task.title, subtitle: "Python 编程实践 · 通过测试后完成", content: <CodingTaskEditor task={task} onComplete={() => { closeModal(); void updateTask(task, undefined, true); }} />, secondary: { label: "关闭", onClick: closeModal } });
      return;
    }
    const isPracticeTask = task.type === "练习" || task.type === "复习" || task.type.startsWith("练习") || task.type.startsWith("复习") || task.title.startsWith("练习：") || task.title.startsWith("复习：");
    if (isPracticeTask && status !== "completed") {
      void startDiagnostic(task);
      return;
    }
    setModal({
      title: task.title,
      subtitle: `${task.type} · ${task.minutes} 分钟 · ${statusLabels[status]}`,
      content: <div className="task-detail"><p>{task.description}</p><div className="detail-grid"><span>学习目标</span><strong>{task.learningGoal ?? content.goal}</strong><span>推荐理由</span><strong>{task.reason}</strong></div><InlineResources knowledgePointIds={task.knowledgePointIds ?? []} title="做之前可以先看" /></div>,
      secondary: { label: "关闭", onClick: closeModal },
      primary: task.type === "能力诊断" && status !== "completed"
        ? { label: "开始诊断", onClick: () => { closeModal(); void startDiagnostic(task); } }
        : status === "completed"
        ? undefined
        : status === "in_progress"
          ? { label: "完成任务", onClick: () => openTaskCompletion(task) }
          : { label: "开始任务", onClick: () => { closeModal(); void updateTask(task); } },
    });
  };

  /**
   * 完成任务前先让用户确认实际用时。
   * 计划分钟数只作为默认值：真实投入由用户自己估计，
   * 这份「计划 vs 实际」的差值会一起写进学习记录，供后续排课校准。
   */
  const openTaskCompletion = (task: LearningTask) => {
    setModal({
      title: "完成任务",
      subtitle: task.title,
      content: <TaskCompletionForm
        plannedMinutes={task.minutes}
        onConfirm={(actualMinutes) => { closeModal(); void updateTask(task, actualMinutes); }}
      />,
      secondary: { label: "取消", onClick: closeModal },
    });
  };

  const openKnowledgeDetail = () => setModal({
    title: "能力图谱详情",
    subtitle: `${currentBook.title} · 当前学习目标关联的知识点`,
    content: <div className="dialog-list">
      {(todayLearning?.knowledgeGraph.nodes ?? []).map((node) => (
        <div className="dialog-list-item" key={node.id}>
          <span className={`dot ${node.status === "good" ? "green" : node.status === "weak" ? "amber" : "blue"}`} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <strong>{node.label}</strong>
            <p>{node.description || (node.accuracy !== null ? `诊断正确率 ${node.accuracy}%` : "尚未评估")}</p>
            <InlineResources knowledgePointIds={[node.id]} title="延伸学习" />
          </div>
        </div>
      ))}
      {(todayLearning?.knowledgeGraph.nodes ?? []).length === 0 && <div className="empty-state"><Icon name="target" size={21} /><strong>还没有能力图谱</strong><span>完成一次能力诊断后生成。</span></div>}
    </div>,
    secondary: { label: "关闭", onClick: closeModal },
  });

  const openEvidence = () => setModal({
    title: "诊断依据详情",
    subtitle: "AI 判断与用户校准分别记录",
    content: <div className="dialog-list"><div className="dialog-list-item"><Icon name="target" size={17} /><div><strong>作答表现</strong><p>{diagnosticResult?.answerPerformance ?? "暂无作答表现。"}</p></div></div><div className="dialog-list-item"><Icon name="clock" size={17} /><div><strong>判断时间</strong><p>{diagnosticResult?.generatedAt ? new Date(diagnosticResult.generatedAt).toLocaleString() : "暂无判断时间。"}</p></div></div><div className="dialog-list-item"><Icon name="file" size={17} /><div><strong>关联范围</strong><p>{diagnosticResult?.relatedScope ?? `${content.goal}及其前置知识点。`}</p></div></div></div>,
    secondary: { label: "关闭", onClick: closeModal },
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

  // 读取图片为本地预览；实际发送仍使用原始File对象。
  const chooseQaAttachment = (file: File | null) => {
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      showToast("暂不支持该文件", "请选择 PNG、JPEG 或 WebP 图片。");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showToast("图片过大", "单张图片不能超过 10MB。");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setQaAttachment({ file, previewUrl: String(reader.result) });
    reader.readAsDataURL(file);
  };

  const askQuestion = async () => {
    const attachment = qaAttachment;
    const question = qaInput.trim() || (attachment ? "请分析这张图片，并结合当前资料进行讲解。" : "");
    if (!question || qaBusy || qaContextBusy) {
      if (!question) showToast("请输入问题", "请输入文字，或先选择一张图片。 ");
      return;
    }
    if (!qaContextToken) {
      setQaError("问答会话尚未创建完成，请稍后重试。");
      return;
    }
    setQaInput("");
    setQaAttachment(null);
    setQaError(null);
    setQaMessages((messages) => [...messages, {
      role: "user",
      text: question,
      attachments: attachment ? [{ fileName: attachment.file.name, fileType: attachment.file.type, fileUrl: attachment.previewUrl }] : undefined,
    }]);
    await runQaRequest(question, false, attachment);
  };

  /**
   * 发起一次资料问答。
   * allowGeneralFallback=true 只会在用户显式点击「用通用模型回答」后传入，
   * 保证无教材出处的答案不会静默出现。
   */
  const runQaRequest = async (question: string, allowGeneralFallback: boolean, attachment?: QaAttachmentDraft | null) => {
    setQaBusy(true);
    setQaError(null);
    try {
      const result = await api.askQuestion({
        bookId,
        question,
        conversationId: qaContextToken ?? undefined,
        sources: content.sources,
        allowGeneralFallback,
        answerMode: allowGeneralFallback ? "direct" : qaAnswerMode,
        learningTaskId: allowGeneralFallback ? null : qaLearningTaskId,
        attachment: attachment?.file,
      });
      if (attachment && result.userMessageId) {
        try {
          const savedAttachments = await api.listQaAttachments(result.userMessageId);
          setQaMessages((messages) => messages.map((message) => (
            message.role === "user" && message.attachments?.[0]?.fileUrl === attachment.previewUrl
              ? { ...message, attachments: savedAttachments.map(({ fileName, fileType, fileUrl }) => ({ fileName, fileType, fileUrl })) }
              : message
          )));
        } catch {
          // 回答已经成功时，附件列表回读失败不应吞掉模型回答；保留本地预览即可。
        }
      }
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

  /** 用户确认后，改用通用模型回答同一个问题 */
  const askWithGeneralModel = async (question: string) => {
    setQaMessages((messages) => messages.filter((message) => !(message.role === "assistant" && message.refused && message.question === question)));
    await runQaRequest(question, true);
  };

  const openDiagnosticAiHelp = async (question: DiagnosticQuestion) => {
    if (qaBusy || qaContextBusy) {
      showToast("AI 求助暂不可用", "请等待当前资料问答完成后再试。");
      return;
    }
    const options = question.options.map((option) => `${option.id}. ${option.text}`).join("\n");
    setQaInput(`请用引导作答的方式帮助我分析这道选择题，先给我思路或提示，不要直接公布答案。\n\n题目：${question.title}\n\n选项：\n${options}`);
    setQaReturnToDiagnostic(true);
    setActiveNav("qa");
    if (qaAnswerMode !== "socratic") await changeQaAnswerMode("socratic");
  };

  const returnToDiagnostic = () => {
    setQaReturnToDiagnostic(false);
    setActiveNav("diagnostic");
  };

  // 未登录时进入认证页；登录成功后由 handleAuthenticated 接管。
  if (!user) return <AuthView onAuthenticated={(session) => handleAuthenticated(session.user)} />;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup"><div className="brand-mark"><Icon name="book-open" size={22} /></div><div><strong>自适应伴学智能体</strong><span>学习闭环</span></div></div>
        <nav className="main-nav" aria-label="主导航">{navigation.map((item) => <button className={`nav-item ${activeNav === item.key ? "active" : ""}`} key={item.key} aria-label={item.label} title={item.label} onClick={() => goTo(item.key)}><Icon name={item.icon} size={19} /><span>{item.label}</span></button>)}</nav>
        <div className="sidebar-bottom"><button className={`nav-item ${activeNav === "profile" ? "active" : ""}`} onClick={() => setActiveNav("profile")}><Icon name="user" size={19} /><span>学习画像</span></button><button className={`nav-item ${activeNav === "goals" ? "active" : ""}`} onClick={() => setActiveNav("goals")}><Icon name="target" size={19} /><span>选书与目标</span></button><button className={`nav-item ${activeNav === "settings" ? "active" : ""}`} onClick={() => setActiveNav("settings")}><Icon name="settings" size={19} /><span>设置</span></button><button className={`nav-item ${activeNav === "help" ? "active" : ""}`} onClick={() => setActiveNav("help")}><Icon name="help" size={19} /><span>帮助</span></button>
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
        {activeNav === "profile" && <LearnerProfileView bookId={bookId} onNotice={showToast} onProfileSaved={ensureWeeklyPlan} />}
        {activeNav === "diagnostic" && <DiagnosticView questions={diagnosticQuestions} index={diagnosticIndex} answers={diagnosticAnswers} skippedQuestions={skippedQuestions} paused={diagnosticPaused} busy={diagnosticBusy} error={diagnosticError} stage={diagnosticStage} result={diagnosticResult} calibration={calibration} calibrationReason={calibrationReason} practice={Boolean(practiceTask)} setAnswer={(id) => currentQuestion && setDiagnosticAnswers((answers) => ({ ...answers, [currentQuestion.id]: id }))} onPrevious={() => setDiagnosticIndex((index) => Math.max(0, index - 1))} onSubmit={submitDiagnostic} onSkip={skipDiagnostic} onPause={() => setDiagnosticPaused(true)} onResume={resumeDiagnostic} onCalibration={setCalibration} onReason={setCalibrationReason} onEvidence={openEvidence} onCalibrationSubmit={submitCalibration} onAiHelp={openDiagnosticAiHelp} />}
        {activeNav === "plan" && (planRegenerating ? <PlanGeneratingView /> : generatedPlan ? <PlanView book={generatedPlan.book} goal={generatedPlan.goal} goalLevel={goalLevel || generatedPlan.goalLevel} tasks={generatedPlan.tasks.map((task) => ({ ...task, status: taskStates[task.id] ?? task.status }))} dailyPlans={generatedPlan.dailyPlans?.map((day) => ({ ...day, tasks: day.tasks.map((task) => ({ ...task, status: taskStates[task.id] ?? task.status })) }))} advice={generatedPlan.advice} resources={generatedPlan.resources} timeBudget={generatedPlan.timeBudget} tab={planTab} setTab={setPlanTab} onOpenTask={openTask} onAdjustPlan={openPlanAdjustment} onOpenSource={openSource} /> : <PlanEmptyView onGenerate={() => void ensureWeeklyPlan(bookId)} onOpenProfile={() => setActiveNav("profile")} />)}
        {activeNav === "records" && <RecordsView records={records} total={recordTotal} summary={recordSummary} page={recordPage} pageSize={recordPageSize} loading={recordsLoading} filter={recordFilter} startDate={recordStartDate} endDate={recordEndDate} setFilter={changeRecordFilter} onDateRangeChange={changeRecordDateRange} onPageChange={setRecordPage} onOpenRecord={openRecord} />}
        {activeNav === "goals" && <GoalsSetupView initialBookId={bookId} onSaved={handleGoalSaved} onSkip={() => setActiveNav("today")} />}
        {activeNav === "settings" && <SettingsView user={user} onUserUpdated={setUser} onLogout={handleLogout} />}
        {activeNav === "resources" && <LearningResourcesView knowledgePointNames={knowledgePointNames} />}
        {activeNav === "help" && <HelpCenterView onNavigate={goTo} />}
        {activeNav === "community" && <CommunityView key={user.userId} userId={user.userId} nickname={user.nickname} course={currentBook.shortTitle} />}
        {activeNav === "motivation" && <MotivationView nickname={user.nickname} bookId={bookId} bookTitle={currentBook.title.replace(/[《》]/g, "")} />}
        {activeNav === "practice" && <PracticeView bookId={bookId} bookTitle={currentBook.title.replace(/^《|》$/g, "")} onProgress={() => void refreshAchievementNotices()} />}
        {activeNav === "qa" && <QaView book={currentBook} sources={qaSources} messages={qaMessages} value={qaInput} busy={qaBusy} error={qaError} answerMode={qaAnswerMode} hasActiveLearningTask={Boolean(qaLearningTaskId)} attachment={qaAttachment} onAttachmentChange={chooseQaAttachment} onRemoveAttachment={() => setQaAttachment(null)} onAnswerModeChange={(mode) => void changeQaAnswerMode(mode)} onFinishSocraticTask={() => void finishSocraticTask()} onChange={setQaInput} onAsk={askQuestion} onNew={clearQaContext} onOpenSource={openSource} onAddPlan={openMaterialPlanEditor} onAskGeneral={askWithGeneralModel} relatedKnowledgePointIds={(todayLearning?.knowledgeGraph.nodes ?? []).filter((node) => node.status === "weak").map((node) => node.id)} />}
        </div>
        </div>
      </main>

      {toast && <div className="toast" role="status"><div className="toast-icon"><Icon name="check" size={17} /></div><div><strong>{toast.title}</strong><span>{toast.message}</span></div></div>}
      {modal && <Modal modal={modal} onClose={closeModal} />}
      {achievementNotices[0] && <div className="achievement-unlock-backdrop"><section className="achievement-unlock-modal" role="dialog" aria-modal="true" aria-labelledby="global-achievement-title"><span className="achievement-unlock-rays" /><div className={`badge-medal ${achievementNotices[0].tone}`}><span>{achievementNotices[0].icon}</span><b><Icon name="check" size={11} /></b></div><span className="eyebrow">ACHIEVEMENT UNLOCKED</span><h2 id="global-achievement-title">解锁新勋章</h2><h3>{achievementNotices[0].title}</h3><p>{achievementNotices[0].detail}</p><button className="primary-button" onClick={closeAchievementNotice}>收下勋章</button></section></div>}
    </div>
  );
}

function buildMessages(content: ReturnType<typeof getBookContent>): QaMessage[] {
  return [{ role: "user", text: content.qaQuestion }, { role: "assistant", text: content.qaAnswer, citations: content.sources }];
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="page-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}

function PlanEmptyView({ onGenerate, onOpenProfile }: { onGenerate: () => void; onOpenProfile: () => void }) {
  return <div className="page-stack"><PageHeader eyebrow="学习闭环 · 目标到任务" title="学习计划" description="学习画像已建立后即可生成未来 7 天的学习计划；每日诊断只负责动态调整后续任务。" /><article className="card empty-state"><Icon name="calendar" size={21} /><strong>暂时没有学习计划</strong><span>如果你已完成学习画像，直接生成计划即可；否则请先补充画像。</span><div className="button-row"><button className="primary-button" onClick={onGenerate}>生成 7 天学习计划</button><button className="outline-button" onClick={onOpenProfile}>查看学习画像</button></div></article></div>;
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
    // 连接真实后端时不再回落到 mockData：
    // 后端没有数据就显示空态，避免把演示内容当成用户的真实学习情况。
    const dashboardContent = {
      ...content,
      goal: dashboard.goal,
      lastLearned: dashboard.continueLearning ? `正在进行：${dashboard.continueLearning.title}` : dashboard.lastLearned,
      recommendation: dashboard.recommendation,
      weeklyProgress: dashboard.weeklyProgress,
      nodes: dashboard.knowledgeGraph.nodes.map((node, index) => ({ label: node.label, tone: node.status === "weak" ? "weak" as const : node.status === "good" ? "good" as const : "learning" as const, ...(nodePositions[index % nodePositions.length]), description: node.description })),
    };
    return <LegacyTodayView book={book} content={dashboardContent} tasks={dashboard.tasks} goTo={continueAction} startDiagnostic={startDiagnostic} onOpenTask={onOpenTask} onOpenKnowledge={onOpenKnowledge} onOpenRecords={onOpenRecords} />;
  }
  return <LegacyTodayView book={book} content={content} tasks={tasks} goTo={goTo} startDiagnostic={startDiagnostic} onOpenTask={onOpenTask} onOpenKnowledge={onOpenKnowledge} onOpenRecords={onOpenRecords} />;
}

function LegacyTodayView({ book, content, tasks, goTo, startDiagnostic, onOpenTask, onOpenKnowledge, onOpenRecords }: { book: Book; content: Omit<ReturnType<typeof getBookContent>, "recommendation"> & { recommendation: { title: string; minutes: number; difficulty?: string; reason: string } | null };  tasks: LearningTask[]; goTo: (key: NavKey) => void; startDiagnostic: () => void; onOpenTask: (task: LearningTask) => void; onOpenKnowledge: () => void; onOpenRecords: () => void }) {
  const completed = tasks.filter((task) => task.status === "completed").length;
  // 后端 /today-learning 返回的真实统计；缺省时按空态展示，不再填充演示数字。
  const weekly = (content as ReturnType<typeof getBookContent> & { weeklyProgress?: TodayLearningResponse["weeklyProgress"] }).weeklyProgress;
  const hasWeekly = Boolean(weekly);
  const progressPercent = Math.max(0, Math.min(100, Math.round(weekly?.progressPercent ?? 0)));
  const studyHours = weekly?.studyDurationHours ?? 0;
  const accuracy = weekly?.accuracy ?? 0;

  // 把每日学习秒数归一化成柱状图高度；无数据时统一显示为最低高度。
  const dailySeconds = (() => {
    const buckets = [0, 0, 0, 0, 0, 0, 0];
    for (const item of weekly?.dailyDuration ?? []) {
      const parsed = new Date(item.date);
      if (Number.isNaN(parsed.getTime())) continue;
      const index = (parsed.getDay() + 6) % 7; // 周一为第 0 格
      buckets[index] += item.durationSeconds;
    }
    return buckets;
  })();
  const peakSeconds = Math.max(...dailySeconds, 0);
  const barHeights = dailySeconds.map((seconds) => (peakSeconds > 0 ? Math.max(6, Math.round((seconds / peakSeconds) * 100)) : 6));

  const headerDescription = hasWeekly
    ? `${book.title} · ${book.subtitle} · 本周已学习 ${studyHours} 小时`
    : `${book.title} · ${book.subtitle}`;

  return <div className="page-stack"><PageHeader eyebrow="持续学习，循序提升" title="今日学习" description={headerDescription} /><section className="stat-grid"><article className="card progress-card"><div className="card-heading"><span>本周进度</span><Icon name="more" size={18} /></div>{hasWeekly ? <><div className="progress-content"><div className="ring-progress" style={{ "--progress": `${progressPercent}%` } as CSSProperties}><span>{progressPercent}<small>%</small></span></div><div className="progress-facts"><div><strong>{weekly?.completedTaskCount ?? 0}/{weekly?.totalTaskCount ?? 0}</strong><span>已完成任务</span></div><div><strong>{studyHours} h</strong><span>学习时长</span></div><div><strong>{accuracy}%</strong><span>正确率</span></div></div></div><div className="mini-bars" aria-label="本周学习时长趋势">{barHeights.map((height, index) => <i style={{ height: `${height}%` }} key={index} />)}</div><div className="week-labels"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div></> : <div className="empty-state"><Icon name="chart" size={21} /><strong>暂无本周数据</strong><span>完成一次诊断或学习任务后这里会显示统计。</span></div>}</article><article className="card recommend-card"><div className="card-heading"><span>今日推荐任务</span>{content.recommendation && <span className="status-pill success">最需要提升</span>}</div>{content.recommendation ? <><h2>{content.recommendation.title}</h2><div className="task-meta"><span><Icon name="clock" size={14} />预计用时 {content.recommendation.minutes} 分钟</span>{content.recommendation.difficulty ? <span>难度 {content.recommendation.difficulty}</span> : null}</div><button className="primary-button" onClick={() => goTo("plan")}>开始学习 <Icon name="arrow-right" size={16} /></button><div className="recommend-reason"><strong>为什么推荐</strong><p>{content.recommendation.reason}</p></div></> : <div className="empty-state"><Icon name="spark" size={21} /><strong>还没有推荐任务</strong><span>完成一次能力诊断后，系统会根据你的薄弱项推荐下一步。</span><button className="primary-button" onClick={startDiagnostic}>开始能力诊断 <Icon name="arrow-right" size={16} /></button></div>}</article><article className="card continue-card"><div className="card-heading"><span>继续学习</span><Icon name="spark" size={18} /></div><div className="target-icon"><Icon name="target" size={23} /></div><h2>{content.goal || "还没有学习目标"}</h2><p>{content.lastLearned ? `上次学习到：${content.lastLearned}` : "选好书籍与目标后，这里会显示你的学习进度。"}</p><button className="outline-button" onClick={() => goTo(content.goal ? "plan" : "goals")}>{content.goal ? "继续学习" : "去设定目标"}</button><button className="text-button" onClick={onOpenRecords}>查看学习记录 <Icon name="arrow-right" size={14} /></button></article></section><section className="dashboard-grid"><article className="card knowledge-card"><div className="card-heading"><div><span>能力图谱</span><small>当前学习目标关联的知识点</small></div><div className="legend"><span><i className="dot green" />掌握良好</span><span><i className="dot blue" />正在学习</span><span><i className="dot amber" />薄弱</span><span><i className="dot neutral" />未评估</span></div></div>{content.nodes.length > 0 ? <div className="knowledge-map"><div className="knowledge-core">{content.goal}</div>{content.nodes.map((node) => <div className={`knowledge-node ${node.tone}`} style={{ left: node.left, top: node.top }} key={node.label}>{node.label}</div>)}</div> : <div className="empty-state"><Icon name="target" size={21} /><strong>还没有该书的能力图谱</strong><span>完成一次能力诊断后，这里会显示每个知识点的掌握情况。</span><button className="outline-button" onClick={startDiagnostic}>开始能力诊断</button></div>}<button className="secondary-button" onClick={onOpenKnowledge} disabled={content.nodes.length === 0}>查看图谱详情 <Icon name="arrow-right" size={15} /></button></article><article className="card task-card"><div className="card-heading"><span>今日任务</span><span className="completion">{completed}/{tasks.length} 已完成</span></div>{tasks.length > 0 ? <div className="task-list">{tasks.map((task) => <TaskRow task={task} key={task.id} onOpen={() => onOpenTask(task)} />)}</div> : <div className="empty-state"><Icon name="calendar" size={21} /><strong>今天还没有任务</strong><span>完成诊断后系统会生成学习计划。</span></div>}<button className="secondary-button full" onClick={() => goTo("plan")}>查看完整计划 <Icon name="arrow-right" size={15} /></button></article></section></div>;
}

/* obsolete duplicate diagnostic view
function DiagnosticView({ questions, index, answers, skippedQuestions, paused, busy, stage, result, calibration, calibrationReason, setAnswer, onPrevious, onSubmit, onSkip, onPause, onResume, onCalibration, onReason, onEvidence, onCalibrationSubmit }: { questions: DiagnosticQuestion[]; index: number; answers: Record<string, string>; skippedQuestions: string[]; paused: boolean; busy: boolean; stage: "question" | "result"; result: DiagnosticResult | null; calibration: Calibration | null; calibrationReason: string; setAnswer: (id: string) => void; onPrevious: () => void; onSubmit: () => void; onSkip: () => void; onPause: () => void; onResume: () => void; onCalibration: (value: Calibration) => void; onReason: (value: string) => void; onEvidence: () => void; onCalibrationSubmit: () => void }) {
  if (stage === "result") return <DiagnosticResult result={result} calibration={calibration} reason={calibrationReason} busy={busy} onCalibration={onCalibration} onReason={onReason} onEvidence={onEvidence} onSubmit={onCalibrationSubmit} />;
  const question = questions[index];
  if (!question) return <div className="page-stack narrow-page"><PageHeader title="暂无诊断题目" description="后端当前没有返回可用的诊断题目。" /><article className="card empty-state"><p>请稍后重新开始诊断。</p></article></div>;
  return <div className="page-stack"><PageHeader eyebrow="持续学习，循序提升" title="今日学习" description={headerDescription} /><section className="stat-grid"><article className="card progress-card"><div className="card-heading"><span>本周进度</span><Icon name="more" size={18} /></div>{hasWeekly ? <><div className="progress-content"><div className="ring-progress" style={{ "--progress": `${progressPercent}%` } as CSSProperties}><span>{progressPercent}<small>%</small></span></div><div className="progress-facts"><div><strong>{weekly?.completedTaskCount ?? 0}/{weekly?.totalTaskCount ?? 0}</strong><span>已完成任务</span></div><div><strong>{studyHours} h</strong><span>学习时长</span></div><div><strong>{accuracy}%</strong><span>正确率</span></div></div></div><div className="mini-bars" aria-label="本周学习时长趋势">{barHeights.map((height, index) => <i style={{ height: `${height}%` }} key={index} />)}</div><div className="week-labels"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div></> : <div className="empty-state"><Icon name="chart" size={21} /><strong>暂无本周数据</strong><span>生成学习计划并完成学习任务后，这里会显示统计。</span></div>}</article><article className="card recommend-card"><div className="card-heading"><span>今日推荐任务</span>{content.recommendation && <span className="status-pill success">最需要提升</span>}</div>{content.recommendation ? <><h2>{content.recommendation.title}</h2><div className="task-meta"><span><Icon name="clock" size={14} />预计用时 {content.recommendation.minutes} 分钟</span>{content.recommendation.difficulty ? <span>难度 {content.recommendation.difficulty}</span> : null}</div><button className="primary-button" onClick={() => goTo("plan")}>开始学习 <Icon name="arrow-right" size={16} /></button><div className="recommend-reason"><strong>为什么推荐</strong><p>{content.recommendation.reason}</p></div></> : <div className="empty-state"><Icon name="spark" size={21} /><strong>还没有推荐任务</strong><span>请先完成选书、学习目标和学习画像，系统会据此生成 7 天计划。</span><button className="primary-button" onClick={() => goTo("profile")}>完善学习画像 <Icon name="arrow-right" size={16} /></button></div>}</article><article className="card continue-card"><div className="card-heading"><span>继续学习</span><Icon name="spark" size={18} /></div><div className="target-icon"><Icon name="target" size={23} /></div><h2>{content.goal || "还没有学习目标"}</h2><p>{content.lastLearned ? `上次学习到：${content.lastLearned}` : "选好书籍与目标后，这里会显示你的学习进度。"}</p><button className="outline-button" onClick={() => goTo(content.goal ? "plan" : "goals")}>{content.goal ? "继续学习" : "去设定目标"}</button><button className="text-button" onClick={onOpenRecords}>查看学习记录 <Icon name="arrow-right" size={14} /></button></article></section><section className="dashboard-grid"><article className="card knowledge-card"><div className="card-heading"><div><span>能力图谱</span><small>当前学习目标关联的知识点</small></div><div className="legend"><span><i className="dot green" />掌握良好</span><span><i className="dot blue" />正在学习</span><span><i className="dot amber" />薄弱</span><span><i className="dot neutral" />未评估</span></div></div>{content.nodes.length > 0 ? <div className="knowledge-map"><div className="knowledge-core">{content.goal}</div>{content.nodes.map((node) => <div className={`knowledge-node ${node.tone}`} style={{ left: node.left, top: node.top }} key={node.label}>{node.label}</div>)}</div> : <div className="empty-state"><Icon name="target" size={21} /><strong>还没有该书的能力图谱</strong><span>每日诊断完成后，这里会显示更新后的掌握情况。</span><button className="outline-button" onClick={startDiagnostic}>开始今日诊断</button></div>}<button className="secondary-button" onClick={onOpenKnowledge} disabled={content.nodes.length === 0}>查看图谱详情 <Icon name="arrow-right" size={15} /></button></article><article className="card task-card"><div className="card-heading"><span>今日任务</span><span className="completion">{completed}/{tasks.length} 已完成</span></div>{tasks.length > 0 ? <div className="task-list">{tasks.map((task) => <TaskRow task={task} key={task.id} onOpen={() => onOpenTask(task)} />)}</div> : <div className="empty-state"><Icon name="calendar" size={21} /><strong>今天还没有任务</strong><span>请先完成选书、学习目标与学习画像以生成学习计划。</span></div>}<button className="secondary-button full" onClick={() => goTo("plan")}>查看完整计划 <Icon name="arrow-right" size={15} /></button></article></section></div>;
}

function readSavedDiagnostic(userId: string, bookId: BookId): SavedDiagnosticSession | null {
  try {
    const raw = window.localStorage.getItem(diagnosticStorageKey(userId, bookId));
    if (!raw) return null;
    const saved = JSON.parse(raw) as SavedDiagnosticSession;
    return saved.diagnosticId && Array.isArray(saved.questions) && saved.questions.length > 0 ? saved : null;
  } catch {
    return null;
  }
}

function clearSavedDiagnostic(userId: string | undefined, bookId: BookId) {
  if (!userId) return;
  try {
    window.localStorage.removeItem(diagnosticStorageKey(userId, bookId));
  } catch {
    // 本地存储不可用时不影响诊断流程。
  }
}
*/

function CodingTaskEditor({ task, onComplete }: { task: LearningTask; onComplete: () => void }) {
  const [code, setCode] = useState("# 在这里编写你的代码\n");
  const [tests, setTests] = useState<string[]>(["assert True"]);
  const [prompt, setPrompt] = useState(task.description);
  const [loading, setLoading] = useState(/^\d+$/.test(task.id));
  const [result, setResult] = useState<{ passed: boolean; stdout: string; stderr: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!/^\d+$/.test(task.id)) return;
    void api.getCodeTaskContent(task.id).then((payload) => {
      setPrompt(payload.prompt ?? task.description);
      setCode(payload.starter_code ?? "# 在这里编写你的代码\n");
      setTests(payload.tests ?? ["assert True"]);
    }).finally(() => setLoading(false));
  }, [task.id, task.description]);
  const run = async () => { setBusy(true); try { setResult(await api.executeCode(code, tests)); } finally { setBusy(false); } };
  return <div className="task-detail coding-task-detail"><div className="coding-prompt"><span className="coding-label">题目要求</span><p>{loading ? "正在加载编程题目…" : prompt}</p></div><label className="code-editor-label">Python 代码<textarea className="code-editor" aria-label="Python代码编辑器" value={code} onChange={(e) => setCode(e.target.value)} rows={14} spellCheck={false} /></label><div className="coding-actions"><button className="primary-button" onClick={() => void run()} disabled={busy || loading}>{busy ? "测试中…" : "运行测试"}</button>{result && <span className={`coding-result ${result.passed ? "success" : "error"}`}>{result.passed ? "✓ 全部测试通过" : `✕ 测试未通过：${result.stderr || "请检查代码"}`}</span>}</div>{result?.passed && <button className="primary-button full coding-complete" onClick={onComplete}>完成编程任务 <Icon name="arrow-right" size={16} /></button>}</div>;
}

function DiagnosticView({ questions, index, answers, skippedQuestions, paused, busy, error, stage, result, calibration, calibrationReason, practice, setAnswer, onPrevious, onSubmit, onSkip, onPause, onResume, onCalibration, onReason, onEvidence, onCalibrationSubmit, onAiHelp }: { questions: DiagnosticQuestion[]; index: number; answers: Record<string, string>; skippedQuestions: string[]; paused: boolean; busy: boolean; error: string | null; stage: "question" | "result"; result: DiagnosticResult | null; calibration: Calibration | null; calibrationReason: string; practice: boolean; setAnswer: (id: string) => void; onPrevious: () => void; onSubmit: () => void; onSkip: () => void; onPause: () => void; onResume: () => void; onCalibration: (value: Calibration) => void; onReason: (value: string) => void; onEvidence: () => void; onCalibrationSubmit: () => void; onAiHelp: (question: DiagnosticQuestion) => void }) {
  if (stage === "result") return <DiagnosticResult result={result} calibration={calibration} reason={calibrationReason} busy={busy} practice={practice} onCalibration={onCalibration} onReason={onReason} onEvidence={onEvidence} onSubmit={onCalibrationSubmit} />;
  if (busy && questions.length === 0) return <div className="page-stack narrow-page"><PageHeader eyebrow="诊断会话" title="正在加载题目" description="正在读取当天学习内容并准备诊断题目，请稍候。" /><article className="card diagnostic-loading-card" role="status" aria-live="polite"><div className="diagnostic-spinner" aria-hidden="true" /><strong>正在加载诊断题目…</strong><span>题目准备完成后会自动显示。</span></article></div>;
  const question = questions[index];
  if (!question) return <div className="page-stack narrow-page"><PageHeader title={error ? "诊断启动失败" : "暂无诊断题目"} description={error ?? "后端当前没有返回可用的诊断题目。"} /><article className="card empty-state"><p>{error ? "请刷新页面并使用数据库账号重新登录后再试。" : "请稍后重新开始诊断。"}</p></article></div>;
  if (paused) return <div className="page-stack narrow-page"><PageHeader eyebrow="诊断已暂停" title="稍后继续诊断" description="已保存的答案不会丢失，回来后可以从当前题目继续。" /><article className="card pause-card"><div className="pause-icon"><Icon name="clock" size={25} /></div><h2>当前进度：第 {index + 1} / {questions.length} 题</h2><p>已完成 {Object.keys(answers).length} 题，跳过 {skippedQuestions.length} 题。</p><button className="primary-button" onClick={onResume}>继续诊断 <Icon name="arrow-right" size={16} /></button></article></div>;
  return <div className="page-stack narrow-page"><PageHeader eyebrow={`诊断会话 · 第 ${index + 1}/${questions.length} 题`} title="能力诊断" description="用少量题目了解当前基础，结果会生成可解释的学习建议。" action={<button className="text-button" onClick={onPause}><Icon name="clock" size={15} />暂时离开</button>} /><div className="diagnostic-progress"><span style={{ width: `${((index + 1) / questions.length) * 100}%` }} /><b>{index + 1} / {questions.length}</b></div><article className="card question-card"><div className="question-top"><span className="question-type">单选题</span><span className="question-tag">{question.tag}</span></div><h2>{question.title}</h2><div className="answer-list">{question.options.map((option) => <button className={`answer-option ${answers[question.id] === option.id ? "selected" : ""}`} key={option.id} onClick={() => setAnswer(option.id)}><span className="option-key">{option.id}</span><span>{option.text}</span>{answers[question.id] === option.id && <Icon name="check-circle" size={18} />}</button>)}</div><div className="question-actions"><div className="question-left-actions"><button className="text-button" disabled={index === 0 || busy} onClick={onPrevious}>上一题</button><button className="text-button" disabled={busy} onClick={onSkip}>跳过</button><button className="ai-help-button" disabled={busy} onClick={() => onAiHelp(question)}><Icon name="spark" size={15} />AI 求助</button></div><button className="primary-button" disabled={busy} onClick={onSubmit}>{busy ? "正在保存…" : index === questions.length - 1 ? "提交诊断" : "提交并继续"} <Icon name="arrow-right" size={16} /></button></div></article><div className="info-banner"><Icon name="info" size={18} /><span>答案会逐题保存，诊断完成后可以查看判断依据。{skippedQuestions.length > 0 && ` 已跳过 ${skippedQuestions.length} 题。`}</span></div></div>;
}

function DiagnosticResult({ result, calibration, reason, busy, practice, onCalibration, onReason, onEvidence, onSubmit }: { result: DiagnosticResult | null; calibration: Calibration | null; reason: string; busy: boolean; practice: boolean; onCalibration: (value: Calibration) => void; onReason: (value: string) => void; onEvidence: () => void; onSubmit: () => void }) {
  if (practice) return <div className="page-stack narrow-page"><PageHeader eyebrow="专项练习完成" title="练习结果" description="本次练习已完成，结果已记录，不会改变后续学习计划。" action={<span className="status-pill success"><Icon name="check" size={14} />已完成</span>} /><article className="card result-card"><div className="result-metrics"><div><strong>{result?.accuracy ?? "—"}</strong><span>正确率</span></div><div><strong>{result?.confidence ?? "—"}</strong><span>完成状态</span></div></div><div className="evidence-summary"><Icon name="info" size={16} /><div><strong>练习说明</strong><p>练习只记录答题表现，不更新掌握能力，也不会重新生成学习计划。</p></div></div><button className="primary-button full" disabled={busy} onClick={onSubmit}>{busy ? "正在保存…" : "完成练习"} <Icon name="arrow-right" size={16} /></button></article></div>;
  return <div className="page-stack"><PageHeader eyebrow="诊断完成" title="测评结果与校准" description="AI 判断和你的自我判断会分别保存，共同影响下一轮学习计划。" action={<span className="status-pill success"><Icon name="check" size={14} />已完成</span>} /><section className="result-grid"><article className="card result-card"><div className="card-heading"><span>AI 评估结果</span><Icon name="spark" size={18} /></div><div className="result-level"><span>能力水平</span><strong>{result?.level ?? "中等偏上"}</strong></div><div className="level-scale"><i style={{ left: "60%" }} /><span>薄弱</span><span>中等</span><span>优秀</span></div><div className="result-metrics"><div><strong>{result?.accuracy ?? "75%"}</strong><span>正确率</span></div><div><strong>{result?.confidence ?? "高"}</strong><span>置信度</span></div></div><div className="evidence-summary"><Icon name="file" size={16} /><div><strong>主要依据</strong><p>{result?.evidence ?? "题目作答结果以及关联知识点表现。"}</p></div></div><button className="secondary-button full" onClick={onEvidence}>查看全部依据 <Icon name="arrow-right" size={15} /></button></article><article className="card result-card calibration-card"><div className="card-heading"><span>用户校准</span><span className="status-pill blue">独立记录</span></div><p className="calibration-intro">你认为自己的真实水平是：</p><div className="calibration-options">{([ ["lower", "低于判断", "我还不太熟悉"], ["same", "基本符合", "这个判断比较准确"], ["higher", "高于判断", "我在其他场景用过"] ] as const).map(([key, title, description]) => <button className={`calibration-option ${calibration === key ? "selected" : ""}`} key={key} onClick={() => onCalibration(key)}><span className="radio-dot" /><div><strong>{title}</strong><small>{description}</small></div>{calibration === key && <Icon name="check-circle" size={18} />}</button>)}</div><label className="reason-input"><span>补充原因（可选）</span><textarea value={reason} onChange={(event) => onReason(event.target.value)} placeholder="例如：我在项目中使用过类似方法。" rows={3} /></label><button className="primary-button full" disabled={!calibration || busy} onClick={onSubmit}>{busy ? "正在提交…" : "提交校准并生成计划"} <Icon name="arrow-right" size={16} /></button></article></section></div>;
}

function LegacyDiagnosticResult({ result, calibration, reason, busy, onCalibration, onReason, onEvidence, onSubmit }: { result: DiagnosticResult | null; calibration: Calibration | null; reason: string; busy: boolean; onCalibration: (value: Calibration) => void; onReason: (value: string) => void; onEvidence: () => void; onSubmit: () => void }) {
  return <div className="page-stack"><PageHeader eyebrow="诊断完成" title="测评结果与校准" description="AI 判断和你的自我判断会分别保存，共同影响下一轮学习计划。" action={<span className="status-pill success"><Icon name="check" size={14} />已完成</span>} /><section className="result-grid"><article className="card result-card"><div className="card-heading"><span>AI 评估结果</span><Icon name="spark" size={18} /></div><div className="result-level"><span>能力水平</span><strong>{result?.level ?? "中等偏上"}</strong></div><div className="level-scale"><i style={{ left: "60%" }} /><span>薄弱</span><span>中等</span><span>优秀</span></div><div className="result-metrics"><div><strong>{result?.accuracy ?? "75%"}</strong><span>正确率</span></div><div><strong>{result?.confidence ?? "高"}</strong><span>置信度</span></div></div><div className="evidence-summary"><Icon name="file" size={16} /><div><strong>主要依据</strong><p>{result?.evidence ?? "题目作答结果以及关联知识点表现。"}</p></div></div><button className="secondary-button full" onClick={onEvidence}>查看全部依据 <Icon name="arrow-right" size={15} /></button></article><article className="card result-card calibration-card"><div className="card-heading"><span>用户校准</span><span className="status-pill blue">独立记录</span></div><p className="calibration-intro">你认为自己的真实水平是：</p><div className="calibration-options">{([ ["lower", "低于判断", "我还不太熟悉"], ["same", "基本符合", "这个判断比较准确"], ["higher", "高于判断", "我在其他场景用过"] ] as const).map(([key, title, description]) => <button className={`calibration-option ${calibration === key ? "selected" : ""}`} key={key} onClick={() => onCalibration(key)}><span className="radio-dot" /><div><strong>{title}</strong><small>{description}</small></div>{calibration === key && <Icon name="check-circle" size={18} />}</button>)}</div><label className="reason-input"><span>补充原因（可选）</span><textarea value={reason} onChange={(event) => onReason(event.target.value)} placeholder="例如：我在项目中使用过类似方法。" rows={3} /></label><button className="primary-button full" disabled={!calibration || busy} onClick={onSubmit}>{busy ? "正在提交…" : "提交校准并生成计划"} <Icon name="arrow-right" size={16} /></button></article></section></div>;
}

/** 把 ISO 日期显示成「今天 / 明天 / 8月25日」。 */
function formatPlanDay(iso: string): string {
  const target = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(target.getTime())) return iso;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((target.getTime() - today.getTime()) / 86400000);
  if (days === 0) return "今天";
  if (days === 1) return "明天";
  if (days === 2) return "后天";
  return `${target.getMonth() + 1}月${target.getDate()}日`;
}

/**
 * 计划的时间预算。
 * paceFactor 是「实际用时 / 计划用时」的历史中位数：>1 表示你通常比 AI 估的慢，
 * 排课会相应放慢；任务自己显示的分钟数仍然是 AI 的原始估计，不会被改写。
 */
function PlanBudgetBlock({ budget }: { budget: PlanTimeBudget }) {
  const off = budget.paceFactor < 0.9 || budget.paceFactor > 1.1;
  return (
    <div className="plan-budget">
      <div className="plan-budget-row"><span>每天安排</span><strong>{budget.dailyMinutes} 分钟</strong></div>
      <div className="plan-budget-row"><span>预计完成</span><strong>{budget.estimatedDays} 天</strong></div>
      {off && (
        <div className="plan-budget-pace">
          <Icon name="info" size={13} />
          <span>
            你最近的实际用时约为计划的 <strong>{budget.paceFactor} 倍</strong>，
            排课已按这个速度{budget.paceFactor > 1 ? "放慢" : "加快"}；
            这些任务实际大约需要 {Math.round(budget.adjustedTotalMinutes / 60 * 10) / 10} 小时。
          </span>
        </div>
      )}
    </div>
  );
}

function PlanCalendarStrip({ days, selectedDate, onSelect }: { days: DailyLearningPlan[]; selectedDate: string | null; onSelect: (date: string) => void }) {
  const initial = selectedDate ? new Date(`${selectedDate}T00:00:00`) : new Date();
  const [month, setMonth] = useState(() => new Date(initial.getFullYear(), initial.getMonth(), 1));
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const cellCount = Math.ceil((first.getDay() + last.getDate()) / 7) * 7;
  const dates = Array.from({ length: cellCount }, (_, index) => { const date = new Date(start); date.setDate(start.getDate() + index); return date; });
  const dayByDate = new Map(days.map((day) => [day.date, day]));
  const monthTitle = `${month.getFullYear()}年${month.getMonth() + 1}月`;
  return <section className="monthly-calendar" aria-label="学习计划日历"><div className="monthly-calendar-header"><button type="button" className="icon-button" aria-label="上个月" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>‹</button><strong>{monthTitle}</strong><button type="button" className="icon-button" aria-label="下个月" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>›</button></div><div className="monthly-calendar-weekdays">{["日", "一", "二", "三", "四", "五", "六"].map((label) => <span key={label}>{label}</span>)}</div><div className="monthly-calendar-grid">{dates.map((date) => { const iso = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; const day = dayByDate.get(iso); const done = Boolean(day && day.tasks.length > 0 && day.tasks.every((task) => task.status === "completed")); return <button type="button" className={`monthly-calendar-date ${date.getMonth() !== month.getMonth() ? "muted" : ""} ${selectedDate === iso ? "active" : ""} ${day ? "has-plan" : ""} ${done ? "done" : ""}`} key={iso} onClick={() => onSelect(iso)}><strong>{date.getDate()}</strong>{day && <span>{done ? "✓" : `${day.tasks.length}项`}</span>}</button>; })}</div></section>;
}

function formatPlanDate(iso: string): string {
  const target = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(target.getTime())) return iso;
  return `${target.getFullYear()}年${target.getMonth() + 1}月${target.getDate()}日`;
}

function formatPlanDateShort(iso: string): string {
  const target = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(target.getTime())) return iso;
  return `${target.getMonth() + 1}/${target.getDate()}`;
}

function PlanWorkloadBars({ days }: { days: DailyLearningPlan[] }) {
  const maxMinutes = Math.max(1, ...days.map((day) => day.tasks.reduce((sum, task) => sum + task.minutes, 0)));
  return <section className="plan-workload card"><div className="plan-panel-heading"><strong>每日学习负载</strong></div><div className="workload-bars" role="img" aria-label="每日任务预计用时柱状图">{days.map((day) => { const minutes = day.tasks.reduce((sum, task) => sum + task.minutes, 0); const done = day.tasks.length > 0 && day.tasks.every((task) => task.status === "completed"); return <div className="workload-column" key={day.date}><div className="workload-track"><i className={done ? "done" : ""} style={{ height: `${Math.max(8, minutes / maxMinutes * 100)}%` }} title={`${formatPlanDate(day.date)}：${minutes} 分钟`} /></div><strong>{minutes}</strong><small>{formatPlanDateShort(day.date)}</small></div>; })}</div></section>;
}

function SelectedDayTasks({ day, selectedDate, onOpenTask }: { day: DailyLearningPlan | null; selectedDate: string | null; onOpenTask: (task: LearningTask) => void }) {
  if (!day) return <section className="selected-day-tasks"><div className="selected-day-heading"><div><strong>{selectedDate ? formatPlanDate(selectedDate) : "请选择日期"}</strong><small>当天没有安排学习任务</small></div><span>0 分钟</span></div><div className="empty-state compact"><Icon name="calendar" size={20} /><strong>暂无任务</strong><span>该日期没有学习计划，可以选择其他日期查看任务。</span></div></section>;
  const tasks = [...day.tasks].sort((a, b) => {
    const rank = (status: string) => status === "in_progress" ? 0 : status === "completed" ? 2 : status === "skipped" ? 3 : 1;
    return rank(a.status) - rank(b.status);
  });
  const completed = tasks.filter((task) => task.status === "completed").length;
  return <section className="selected-day-tasks"><div className="selected-day-heading"><div><strong>{formatPlanDate(day.date)}</strong><small>{completed}/{tasks.length} 项任务已完成</small></div><span>{tasks.reduce((sum, task) => sum + task.minutes, 0)} 分钟</span></div><p className="selected-day-reason">{day.reason}</p>{tasks.length > 0 ? <div className="selected-day-list">{tasks.map((task) => <button type="button" className={`selected-day-task ${task.status}`} key={task.id} onClick={() => onOpenTask(task)}><span className={`timeline-dot ${task.status}`} /><div><strong>{task.title}</strong><small>{task.type} · {task.minutes} 分钟</small></div><span className={`status-pill ${task.status}`}>{statusLabels[task.status]}</span><Icon name="chevron-right" size={16} /></button>)}</div> : <p>当天暂时没有任务。</p>}</section>;
}

function PlanView({ book, goal, goalLevel, tasks, dailyPlans, advice, resources, timeBudget, tab, setTab, onOpenTask, onAdjustPlan, onOpenSource }: { book: { title: string; shortTitle: string }; goal: string; goalLevel: string; tasks: LearningTask[]; dailyPlans?: DailyLearningPlan[]; advice: string[]; resources: Source[]; timeBudget?: PlanTimeBudget; tab: "overview" | "knowledge"; setTab: (tab: "overview" | "knowledge") => void; onOpenTask: (task: LearningTask) => void; onAdjustPlan: () => void; onOpenSource: (source: Source) => void }) {
  const completed = tasks.filter((task) => task.status === "completed").length;
  const days = dailyPlans ?? [];
  // 每次进入计划页，先展示含有“进行中”任务的日期；没有时才回退到第一个未完成日。
  const preferredDay = days.find((day) => day.tasks.some((task) => task.status === "in_progress"))
    ?? days.find((day) => day.tasks.some((task) => task.status !== "completed" && task.status !== "skipped"))
    ?? days[0];
  const [expandedDay, setExpandedDay] = useState<string | null>(() => preferredDay?.date ?? null);
  return <div className="page-stack">
    <PageHeader eyebrow="学习闭环 · 目标到任务" title="学习计划" description={book.title} action={<div className="header-actions"><button className="primary-button" onClick={onAdjustPlan}><Icon name="spark" size={15} />调整并生成计划</button></div>} />
    {days.length > 0 && <section className="plan-top-grid"><PlanWorkloadBars days={days} /><PlanCalendarStrip days={days} selectedDate={expandedDay} onSelect={setExpandedDay} /></section>}
    <section className="plan-content-grid">
    {tab === "overview" && days.length > 0 && <SelectedDayTasks day={days.find((item) => item.date === expandedDay) ?? null} selectedDate={expandedDay} onOpenTask={onOpenTask} />}
    <section className="plan-layout plan-workspace">
      <article className="card plan-summary plan-overview-card"><span className="section-label">计划目标</span><h2>{goal}</h2><p>{goalLevel}</p><div className="ring-progress small" style={{ "--progress": `${tasks.length ? Math.round((completed / tasks.length) * 100) : 0}%` } as CSSProperties}><span>{tasks.length ? Math.round((completed / tasks.length) * 100) : 0}<small>%</small></span></div><div className="plan-summary-count"><strong>{completed}/{tasks.length}</strong><span>任务已完成</span></div>{timeBudget && <PlanBudgetBlock budget={timeBudget} />}<button className="secondary-button full" onClick={onAdjustPlan}>调整并生成计划</button></article>
    <article className="card plan-table-card plan-board-card"><div className="plan-board-heading"><div><strong>本周学习计划</strong><small>按天查看任务，点击任务进入学习</small></div><span>{days.length} 天</span></div><div className="plan-tabs"><button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>计划总览</button><button className={tab === "knowledge" ? "active" : ""} onClick={() => setTab("knowledge")}>知识点列表</button></div>{tab === "overview" ? <>{days.length > 0 ? <div className="plan-table daily-plan-list">{days.map((day, dayIndex) => { const open = expandedDay === day.date; const done = day.tasks.filter((task) => task.status === "completed").length; return <div className="daily-plan-group" key={day.date}><button className="plan-row plan-row-button daily-plan-row" onClick={() => setExpandedDay(open ? null : day.date)}><div className="plan-task"><span className={`timeline-dot ${done === day.tasks.length && day.tasks.length > 0 ? "completed" : "todo"}`} /><div><strong>第 {dayIndex + 1} 天学习计划</strong><small>{formatPlanDay(day.date)} · {day.tasks.length ? `${done}/${day.tasks.length} 项任务` : "正在准备当天任务"}</small></div></div><span className="status-pill">{done === day.tasks.length && day.tasks.length > 0 ? "已完成" : "待开始"}</span><span className="duration">{day.tasks.reduce((sum, task) => sum + task.minutes, 0) ? `${day.tasks.reduce((sum, task) => sum + task.minutes, 0)} 分钟` : "—"}</span><span className="reason">{day.reason}</span></button>{open && <div className="daily-plan-details">{day.tasks.length ? day.tasks.map((task) => <button className="plan-row plan-row-button" key={task.id} onClick={() => onOpenTask(task)}><div className="plan-task"><span className={`timeline-dot ${task.status}`} /><div><strong>{task.title}</strong><small>{task.type}</small></div></div><span className={`status-pill ${task.status}`}>{statusLabels[task.status]}</span><span className="duration">{task.minutes} 分钟</span><span className="reason">{task.reason}</span></button>) : <p>当天开始后，系统会先安排诊断，再生成后续学习任务。</p>}</div>}</div>; })}</div> : <div className="plan-table">{tasks.map((task) => <button className="plan-row plan-row-button" key={task.id} onClick={() => onOpenTask(task)}><div className="plan-task"><span className={`timeline-dot ${task.status}`} /><div><strong>{task.title}</strong><small>{task.type}{task.expectedCompletionDate ? ` · 排在 ${formatPlanDay(task.expectedCompletionDate)}` : ""}</small></div></div><span className={`status-pill ${task.status}`}>{statusLabels[task.status]}</span><span className="duration">{task.minutes ? `${task.minutes} 分钟` : "—"}</span><span className="reason">{task.reason}</span></button>)}</div>}</> : <div className="knowledge-list">{tasks.map((task) => <button className="knowledge-list-item" key={task.id} onClick={() => onOpenTask(task)}><span className="task-status in_progress"><Icon name="target" size={13} /></span><div><strong>{task.title}</strong><small>{task.description}</small></div><Icon name="chevron-right" size={16} /></button>)}</div>}</article>
    </section>
    <section className="plan-bottom-grid"><article className="card advice-card"><div className="card-heading"><span>学习建议</span><Icon name="spark" size={18} /></div>{advice.map((item, index) => index === 0 ? <p key={item}>{item}</p> : <div key={item}>{item}</div>)}</article><article className="card resources-card"><div className="card-heading"><span>推荐资料</span><Icon name="file" size={18} /></div>{resources.map((source) => <button key={source.id} onClick={() => onOpenSource(source)}><Icon name={source.type === "教材" ? "book" : "file"} size={16} /><span>{source.type} · {source.title}</span><Icon name="arrow-up-right" size={14} /></button>)}</article></section>
    </section>
  </div>;
}

function LegacyPlanView({ book, goal, goalLevel, tasks, tab, setTab, onOpenTask, onAdjustGoal, onOpenSource }: { book: Book; goal: string; goalLevel: string; tasks: LearningTask[]; tab: "overview" | "knowledge"; setTab: (tab: "overview" | "knowledge") => void; onOpenTask: (task: LearningTask) => void; onAdjustGoal: () => void; onOpenSource: (source: Source) => void }) {
  const completed = tasks.filter((task) => task.status === "completed").length;
  return <div className="page-stack"><PageHeader eyebrow="学习闭环 · 目标到任务" title="学习计划" description={`${book.title} · 系统会根据目标、诊断结果、用户校准和时间约束排列任务。`} action={<button className="outline-button" onClick={onAdjustGoal}>调整目标</button>} /><section className="plan-layout"><article className="card plan-summary"><span className="section-label">计划目标</span><h2>{goal}</h2><p>{goalLevel}</p><div className="ring-progress small" style={{ "--progress": `${tasks.length ? Math.round((completed / tasks.length) * 100) : 0}%` } as CSSProperties}><span>{tasks.length ? Math.round((completed / tasks.length) * 100) : 0}<small>%</small></span></div><button className="secondary-button full" onClick={onAdjustGoal}>调整目标</button></article><article className="card plan-table-card"><div className="plan-tabs"><button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>计划总览</button><button className={tab === "knowledge" ? "active" : ""} onClick={() => setTab("knowledge")}>知识点列表</button></div>{tab === "overview" ? <><div className="plan-table-head"><span>任务</span><span>状态</span><span>预计用时</span><span>推荐理由</span></div><div className="plan-table">{tasks.map((task) => <button className="plan-row plan-row-button" key={task.id} onClick={() => onOpenTask(task)}><div className="plan-task"><span className={`timeline-dot ${task.status}`} /><div><strong>{task.title}</strong><small>{task.type}{task.expectedCompletionDate ? ` · 排在 ${formatPlanDay(task.expectedCompletionDate)}` : ""}</small></div></div><span className={`status-pill ${task.status}`}>{statusLabels[task.status]}</span><span className="duration">{task.minutes ? `${task.minutes} 分钟` : "—"}</span><span className="reason">{task.reason}</span></button>)}</div></> : <div className="knowledge-list">{tasks.map((task) => <button className="knowledge-list-item" key={task.id} onClick={() => onOpenTask(task)}><span className="task-status in_progress"><Icon name="target" size={13} /></span><div><strong>{task.title}</strong><small>{task.description}</small></div><Icon name="chevron-right" size={16} /></button>)}</div>}</article></section><section className="plan-bottom-grid"><article className="card advice-card"><div className="card-heading"><span>学习建议</span><Icon name="spark" size={18} /></div><p>今天建议先完成{tasks.find((task) => task.status === "in_progress")?.title ?? tasks[0].title}，再进行一次短复测。</p><ul><li>保持连续学习，减少间隔过长</li><li>完成后进行 1 次短复测</li></ul></article><article className="card resources-card"><div className="card-heading"><span>推荐资料</span><Icon name="file" size={18} /></div><button onClick={() => onOpenSource({ id: "plan-book", type: "教材", title: `${book.shortTitle} · 重点章节`, location: "第 3 章", excerpt: `这份资料用于支持“${goal}”的学习目标。` })}><Icon name="book" size={16} /><span>教材 · 重点章节</span><Icon name="arrow-up-right" size={14} /></button><button onClick={() => onOpenSource({ id: "plan-note", type: "讲义", title: `${book.shortTitle} · 复习讲义`, location: "第 2 节", excerpt: "建议在完成练习后回看这份讲义，确认关键概念之间的关系。" })}><Icon name="file" size={16} /><span>讲义 · 复习重点</span><Icon name="arrow-up-right" size={14} /></button></article></section></div>;
}

function RecordsView({ records, total, summary, page, pageSize, loading, filter, startDate, endDate, setFilter, onDateRangeChange, onPageChange, onOpenRecord }: { records: RecordItem[]; total: number; summary: LearningRecordSummary | null; page: number; pageSize: number; loading: boolean; filter: "all" | RecordItem["category"]; startDate: string; endDate: string; setFilter: (filter: "all" | RecordItem["category"]) => void; onDateRangeChange: (startDate: string, endDate: string) => void; onPageChange: (page: number) => void; onOpenRecord: (record: RecordItem) => void }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const visiblePageCount = Math.min(10, pageCount);
  const firstVisiblePage = Math.min(Math.max(1, page), Math.max(1, pageCount - visiblePageCount + 1));
  const visiblePages = Array.from({ length: visiblePageCount }, (_, index) => firstVisiblePage + index);

  return <div className="page-stack">
    <PageHeader eyebrow="学习事件 · 可追溯" title="学习记录" description="默认展示当天记录；可通过日期范围查看历史活动。" action={<div className="record-filters"><label className="filter-select"><Icon name="filter" size={15} /><select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)} aria-label="筛选学习记录"><option value="all">全部记录</option><option value="profile">人物画像</option><option value="task">学习任务</option><option value="diagnostic">能力诊断</option><option value="qa">资料问答</option></select></label><label className="record-date-field"><span>从</span><input type="date" value={startDate} max={endDate} onChange={(event) => onDateRangeChange(event.target.value, endDate)} aria-label="记录起始日期" /></label><label className="record-date-field"><span>到</span><input type="date" value={endDate} min={startDate} onChange={(event) => onDateRangeChange(startDate, event.target.value)} aria-label="记录结束日期" /></label></div>} />
    <RecordInsights summary={summary} />
    <section className="records-layout"><article className="card record-timeline"><div className="card-heading"><span>{startDate === endDate ? "当天活动" : "范围内活动"}</span><span className="completion">{loading ? "正在加载" : `共 ${total} 个结果`}</span></div>{loading ? <EmptyState text="正在加载学习记录" /> : records.length === 0 ? <EmptyState text="这个日期范围内暂时没有符合条件的记录" /> : records.map((item) => <div className="record-item" key={item.id}><div className={`record-icon ${item.tone}`}><Icon name={item.icon} size={16} /></div><div className="record-copy"><strong>{item.title}</strong><p>{item.description}</p><span>{item.time}</span></div><button className="icon-button" onClick={() => onOpenRecord(item)} aria-label="查看记录详情"><Icon name="chevron-right" size={17} /></button></div>)}{pageCount > 1 && <div className="record-pagination" aria-label="学习记录分页"><button className="pagination-arrow" onClick={() => onPageChange(page - 1)} disabled={loading || page === 1} aria-label="上一页"><Icon name="chevron-left" size={15} /></button>{visiblePages.map((pageNumber) => <button key={pageNumber} className={pageNumber === page ? "active" : ""} onClick={() => onPageChange(pageNumber)} disabled={loading}>{pageNumber}</button>)}<button className="pagination-arrow" onClick={() => onPageChange(page + 1)} disabled={loading || page === pageCount} aria-label="下一页"><Icon name="chevron-right" size={15} /></button></div>}</article></section>
  </div>;
}

function QaView({
  book,
  sources,
  messages,
  value,
  busy,
  error,
  answerMode,
  hasActiveLearningTask,
  attachment,
  onAttachmentChange,
  onRemoveAttachment,
  onAnswerModeChange,
  onFinishSocraticTask,
  onChange,
  onAsk,
  onNew,
  onOpenSource,
  onAddPlan,
  onAskGeneral,
  relatedKnowledgePointIds,
}: {
  book: Book;
  sources: Source[];
  messages: QaMessage[];
  value: string;
  busy: boolean;
  error: string | null;
  answerMode: QaAnswerMode;
  hasActiveLearningTask: boolean;
  attachment: QaAttachmentDraft | null;
  onAttachmentChange: (file: File | null) => void;
  onRemoveAttachment: () => void;
  onAnswerModeChange: (mode: QaAnswerMode) => void;
  onFinishSocraticTask: () => void;
  onChange: (value: string) => void;
  onAsk: () => void;
  onNew: () => void;
  onOpenSource: (source: Source) => void;
  onAddPlan: () => void;
  onAskGeneral: (question: string) => void;
  relatedKnowledgePointIds: string[];
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sourceBookTitle = (source: Source) =>
    books.find((item) => item.id === source.bookId)?.title ?? book.title;
  const uniqueSources = mergeSourcesByChapter(sources);
  // 清空会写入上下文重置标记；回答生成期间禁止清空，避免在途回答越过重置边界。
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="资料驱动 · 保留引用"
        title="资料问答"
        description="围绕当前学习内容和学习目标提问，回答会保留资料出处。"
        action={
          <button
            className="outline-button"
            onClick={onNew}
            title="清空当前对话，重新开始一轮提问"
          >
            清空对话 <Icon name="trash" size={15} />
          </button>
        }
      />
      <section className="qa-layout">
        <article className="card conversation-card">
          <div className="conversation-head">
            <div>
              <span className="section-label">当前范围</span>
              <strong>
                {book.title} · {book.subtitle}
              </strong>
            </div>
            <span className="status-pill blue">已绑定知识点</span>
          </div>
          <div className="qa-mode-bar">
            <div className="qa-mode-switch" aria-label="回答方式">
              <button
                className={answerMode === "direct" ? "active" : ""}
                onClick={() => onAnswerModeChange("direct")}
                disabled={busy}
              >
                直接回答
              </button>
              <button
                className={answerMode === "socratic" ? "active" : ""}
                onClick={() => onAnswerModeChange("socratic")}
                disabled={busy}
              >
                引导作答
              </button>
            </div>
            <span>
              {answerMode === "socratic"
                ? "每轮只给一个问题或提示，不直接泄露完整答案"
                : "直接根据教材给出有出处的回答"}
            </span>
            {answerMode === "socratic" && hasActiveLearningTask && (
              <button
                className="qa-finish-task"
                onClick={onFinishSocraticTask}
                disabled={busy}
              >
                结束本轮引导
              </button>
            )}
          </div>
          <div className="message-list">
            {messages.map((message, index) => (
              <div
                className={`message ${message.role}`}
                key={`${message.role}-${index}`}
              >
                <span className="message-avatar">
                  {message.role === "assistant" ? "✦" : "我"}
                </span>
                <div>
                  {message.fromGeneralModel && (
                    <div className="general-model-tag">
                      <Icon name="alert" size={13} />
                      此回答来自通用模型，未经教材验证，不计入学习记录
                    </div>
                  )}
                  {message.role === "assistant" &&
                    message.answerMode === "socratic" && (
                      <div className="socratic-tag">
                        引导作答{message.socraticCompleted ? " · 已完成" : ""}
                      </div>
                    )}
                  {message.attachments?.map((item) => (
                    <a
                      className="qa-message-attachment"
                      href={item.fileUrl}
                      key={item.fileUrl}
                      rel="noreferrer"
                      target="_blank"
                    >
                      <img src={item.fileUrl} alt={item.fileName} />
                      <span>
                        <Icon name="file" size={13} />
                        {item.fileName}
                      </span>
                    </a>
                  ))}
                  <p
                    className={
                      message.fromGeneralModel
                        ? "general-model-answer"
                        : undefined
                    }
                  >
                    {message.text}
                  </p>
                  {message.role === "assistant" &&
                    message.refused &&
                    message.answerMode !== "socratic" && (
                      <div className="qa-fallback">
                        <span>资料里没有找到能支持这个问题的依据。</span>
                        <button
                          type="button"
                          onClick={() => onAskGeneral(message.question ?? "")}
                          disabled={!message.question}
                        >
                          用通用模型回答（无教材引用）
                        </button>
                        <InlineResources
                          knowledgePointIds={relatedKnowledgePointIds}
                          title="或者看看这些资料"
                        />
                      </div>
                    )}
                  {message.role === "assistant" &&
                    !message.refused &&
                    !message.fromGeneralModel && (
                      <div className="citation-row">
                        {mergeSourcesByChapter(
                          message.citations ?? sources,
                        ).map((source) => (
                          <button
                            key={sourceChapterKey(source)}
                            onClick={() => onOpenSource(source)}
                          >
                            <Icon name="file" size={14} />
                            <span>
                              <strong>
                                {sourceBookTitle(source)} ·{" "}
                                {source.contentUnitId || source.title}
                              </strong>
                              <small>{source.location}</small>
                            </span>
                            <Icon name="chevron-right" size={14} />
                          </button>
                        ))}
                      </div>
                    )}
                </div>
              </div>
            ))}
            {busy && (
              <div className="message assistant">
                <span className="message-avatar">✦</span>
                <div className="typing-state">
                  {answerMode === "socratic"
                    ? "正在判断下一步引导…"
                    : "正在查找相关资料…"}
                </div>
              </div>
            )}
            {error && (
              <div className="inline-error" role="alert">
                <Icon name="info" size={16} />
                <span>{error}</span>
                <button onClick={onAsk}>重新发送</button>
              </div>
            )}
          </div>
          {attachment && (
            <div className="qa-attachment-preview">
              <img src={attachment.previewUrl} alt={attachment.file.name} />
              <div>
                <strong>{attachment.file.name}</strong>
                <small>
                  {(attachment.file.size / 1024 / 1024).toFixed(2)} MB
                </small>
              </div>
              <button
                type="button"
                onClick={onRemoveAttachment}
                disabled={busy}
                aria-label="移除图片"
              >
                <Icon name="close" size={15} />
              </button>
            </div>
          )}
          <div className="chat-composer">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              hidden
              onChange={(event) => {
                onAttachmentChange(event.currentTarget.files?.[0] ?? null);
                event.currentTarget.value = "";
              }}
            />
            <button
              type="button"
              className="qa-attach-button"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
              aria-label="添加图片"
              title="添加图片（PNG、JPEG 或 WebP，最大 10 MB）"
            >
              <Icon name="image" size={17} />
              <span>图片</span>
            </button>
            <textarea
              value={value}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  onAsk();
                }
              }}
              placeholder={
                answerMode === "socratic"
                  ? hasActiveLearningTask
                    ? "回答导师的问题（Shift + Enter 换行）"
                    : "输入一道题，开始引导作答"
                  : "继续提问（Shift + Enter 换行）"
              }
              rows={2}
            />
            <button
              className="send-button"
              onClick={onAsk}
              disabled={busy}
              aria-label="发送问题"
            >
              <Icon name="send" size={17} />
            </button>
          </div>
          <div className="suggestion-row">
            {answerMode === "socratic" ? (
              <>
                <button onClick={() => onChange("我不太确定，请给我一个提示")}>
                  给我一个提示
                </button>
                <button
                  onClick={() => onChange("我认为可以先从核心概念开始分析")}
                >
                  我先说说思路
                </button>
              </>
            ) : (
              <>
                <button onClick={() => onChange("这个概念如何举例？")}>
                  这个概念如何举例？
                </button>
                <button onClick={() => onChange("需要哪些前置知识？")}>
                  需要哪些前置知识？
                </button>
              </>
            )}
          </div>
        </article>
        <aside className="card source-card">
          <div className="card-heading">
            <span>来源详情</span>
            <Icon name="info" size={17} />
          </div>
          {uniqueSources.length === 0 ? (
            <div className="source-empty">提问后显示检索到的资料来源</div>
          ) : (
            uniqueSources.map((source) => (
              <button
                className="source-block"
                key={sourceChapterKey(source)}
                onClick={() => onOpenSource(source)}
              >
                <Icon name="file" size={15} />
                <strong>
                  {sourceBookTitle(source)} ·{" "}
                  {source.contentUnitId || source.title}
                </strong>
              </button>
            ))
          )}
        </aside>
      </section>
    </div>
  );
}

function RecordInsights({ summary }: { summary: LearningRecordSummary | null }) {
  if (!summary) return null;
  const stats = [
    { label: "今日活动", value: summary.today.activityCount, unit: "次", icon: "chart" as const },
    { label: "完成任务", value: summary.today.completedTasks, unit: "项", icon: "check" as const },
    { label: "专注时长", value: summary.today.studyMinutes, unit: "分钟", icon: "clock" as const },
    { label: "诊断正确率", value: summary.today.diagnosticAccuracy ?? "—", unit: summary.today.diagnosticAccuracy === null ? "" : "%", icon: "target" as const },
  ];
  const peak = Math.max(...summary.calendar.map((day) => day.activityCount), 1);
  const monthLabel = summary.calendar[0] ? new Date(`${summary.calendar[0].date}T00:00:00`).toLocaleDateString("zh-CN", { year: "numeric", month: "long" }) : "本月";
  return <section className="record-insights"><div className="record-stat-grid">{stats.map((stat) => <article className="card record-stat" key={stat.label}><Icon name={stat.icon} size={16} /><span>{stat.label}</span><strong>{stat.value}<small>{stat.unit}</small></strong></article>)}</div><article className="card record-calendar"><div><span className="section-label">{monthLabel}学习足迹</span><strong>保持节奏，稳步向前</strong></div><div className="activity-heatmap" aria-label={`${monthLabel}学习日历`}>{summary.calendar.map((day) => <span key={day.date} data-date={day.date} title={`${day.date} · ${day.activityCount} 次活动`} style={{ "--activity-level": day.activityCount / peak } as CSSProperties} />)}</div><small>悬停方格可查看日期；颜色越深表示活动越多。</small></article></section>;
}

function LegacyQaView({ book, sources, messages, value, busy, error, answerMode, hasActiveLearningTask, returnToDiagnostic, onReturnToDiagnostic, onAnswerModeChange, onFinishSocraticTask, onChange, onAsk, onNew, onOpenSource, onAddPlan, onAskGeneral, relatedKnowledgePointIds }: { book: Book; sources: Source[]; messages: QaMessage[]; value: string; busy: boolean; error: string | null; answerMode: QaAnswerMode; hasActiveLearningTask: boolean; returnToDiagnostic: boolean; onReturnToDiagnostic: () => void; onAnswerModeChange: (mode: QaAnswerMode) => void; onFinishSocraticTask: () => void; onChange: (value: string) => void; onAsk: () => void; onNew: () => void; onOpenSource: (source: Source) => void; onAddPlan: () => void; onAskGeneral: (question: string) => void; relatedKnowledgePointIds: string[] }) {
  const sourceBookTitle = (source: Source) => books.find((item) => item.id === source.bookId)?.title ?? book.title;
  const uniqueSources = mergeSourcesByChapter(sources);
  // 清空会写入上下文重置标记；回答生成期间禁止清空，避免在途回答越过重置边界。
  return <div className="page-stack"><PageHeader eyebrow="资料驱动 · 保留引用" title="资料问答" description="围绕当前学习内容和学习目标提问，回答会保留资料出处。" action={<div className="qa-header-actions">{returnToDiagnostic && <button className="outline-button" onClick={onReturnToDiagnostic}><Icon name="chevron-left" size={15} />返回答题</button>}<button className="outline-button" onClick={onNew} title="清空当前对话，重新开始一轮提问">清空对话 <Icon name="trash" size={15} /></button></div>} /><section className="qa-layout"><article className="card conversation-card"><div className="conversation-head"><div><span className="section-label">当前范围</span><strong>{book.title} · {book.subtitle}</strong></div><span className="status-pill blue">已绑定知识点</span></div><div className="qa-mode-bar"><div className="qa-mode-switch" aria-label="回答方式"><button className={answerMode === "direct" ? "active" : ""} onClick={() => onAnswerModeChange("direct")} disabled={busy}>直接回答</button><button className={answerMode === "socratic" ? "active" : ""} onClick={() => onAnswerModeChange("socratic")} disabled={busy}>引导作答</button></div><span>{answerMode === "socratic" ? "每轮只给一个问题或提示，不直接泄露完整答案" : "直接根据教材给出有出处的回答"}</span>{answerMode === "socratic" && hasActiveLearningTask && <button className="qa-finish-task" onClick={onFinishSocraticTask} disabled={busy}>结束本轮引导</button>}</div><div className="message-list">{messages.map((message, index) => <div className={`message ${message.role}`} key={`${message.role}-${index}`}><span className="message-avatar">{message.role === "assistant" ? "✦" : "我"}</span><div>{message.fromGeneralModel && <div className="general-model-tag"><Icon name="alert" size={13} />此回答来自通用模型，未经教材验证，不计入学习记录</div>}{message.role === "assistant" && message.answerMode === "socratic" && <div className="socratic-tag">引导作答{message.socraticCompleted ? " · 已完成" : ""}</div>}<p className={message.fromGeneralModel ? "general-model-answer" : undefined}>{message.text}</p>{message.role === "assistant" && message.refused && message.answerMode !== "socratic" && <div className="qa-fallback"><span>资料里没有找到能支持这个问题的依据。</span><button type="button" onClick={() => onAskGeneral(message.question ?? "")} disabled={!message.question}>用通用模型回答（无教材引用）</button><InlineResources knowledgePointIds={relatedKnowledgePointIds} title="或者看看这些资料" /></div>}{message.role === "assistant" && !message.refused && !message.fromGeneralModel && <div className="citation-row">{mergeSourcesByChapter(message.citations ?? sources).map((source) => <button key={sourceChapterKey(source)} onClick={() => onOpenSource(source)}><Icon name="file" size={14} /><span><strong>{sourceBookTitle(source)} · {source.contentUnitId || source.title}</strong><small>{source.location}</small></span><Icon name="chevron-right" size={14} /></button>)}</div>}</div></div>)}{busy && <div className="message assistant"><span className="message-avatar">✦</span><div className="typing-state">{answerMode === "socratic" ? "正在判断下一步引导…" : "正在查找相关资料…"}</div></div>}{error && <div className="inline-error" role="alert"><Icon name="info" size={16} /><span>{error}</span><button onClick={onAsk}>重新发送</button></div>}</div><div className="chat-composer"><textarea value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onAsk(); } }} placeholder={answerMode === "socratic" ? (hasActiveLearningTask ? "回答导师的问题（Shift + Enter 换行）" : "输入一道题，开始引导作答") : "继续提问（Shift + Enter 换行）"} rows={2} /><button className="send-button" onClick={onAsk} disabled={busy} aria-label="发送问题"><Icon name="send" size={17} /></button></div><div className="suggestion-row">{answerMode === "socratic" ? <><button onClick={() => onChange("我不太确定，请给我一个提示")}>给我一个提示</button><button onClick={() => onChange("我认为可以先从核心概念开始分析")}>我先说说思路</button></> : <><button onClick={() => onChange("这个概念如何举例？")}>这个概念如何举例？</button><button onClick={() => onChange("需要哪些前置知识？")}>需要哪些前置知识？</button></>}</div></article><aside className="card source-card"><div className="card-heading"><span>来源详情</span><Icon name="info" size={17} /></div>{uniqueSources.length === 0 ? <div className="source-empty">提问后显示检索到的资料来源</div> : uniqueSources.map((source) => <button className="source-block" key={sourceChapterKey(source)} onClick={() => onOpenSource(source)}><Icon name="file" size={15} /><strong>{sourceBookTitle(source)} · {source.contentUnitId || source.title}</strong></button>)}{uniqueSources.length > 0 && <button className="secondary-button full" onClick={onAddPlan}>加入学习计划 <Icon name="plus" size={15} /></button>}</aside></section></div>;
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

/** 实际用时的上限：24 小时。再长的单次任务不合理，但也不该由前端替用户否定。 */
const MAX_ACTUAL_MINUTES = 1440;
/** 超过这个时长只提醒、不拦截。 */
const LONG_SESSION_MINUTES = 480;

function TaskCompletionForm({ plannedMinutes, onConfirm }: { plannedMinutes: number; onConfirm: (actualMinutes: number) => void }) {
  const [minutes, setMinutes] = useState(plannedMinutes || 20);
  const diff = minutes - plannedMinutes;
  const clamp = (value: number) => Math.min(MAX_ACTUAL_MINUTES, Math.max(1, value));
  // 滑块保持「围绕计划值的精细调节」，拉到 1440 会让 15 分钟的任务没法微调；
  // 想填更长直接在右边数字框输入，上限 24 小时。
  const sliderMax = Math.min(MAX_ACTUAL_MINUTES, Math.max(plannedMinutes * 4, 120));
  const longSession = minutes > LONG_SESSION_MINUTES;
  const hours = (minutes / 60).toFixed(minutes % 60 === 0 ? 0 : 1);
  return (
    <div className="completion-form">
      <p>这个任务你实际花了多久？计划是 <strong>{plannedMinutes} 分钟</strong>，如果不一样请改成真实用时。</p>
      <label className="auth-field">
        <span>实际用时</span>
        <div className="hours-row">
          <input type="range" min={1} max={sliderMax} value={Math.min(minutes, sliderMax)} onChange={(event) => setMinutes(Number(event.target.value))} aria-label="实际用时滑块" />
          <div className="hours-input">
            <input type="number" min={1} max={MAX_ACTUAL_MINUTES} value={minutes} onChange={(event) => setMinutes(clamp(Number(event.target.value) || 1))} aria-label="实际用时分钟数" />
            <span>分钟</span>
          </div>
        </div>
      </label>
      {longSession ? (
        <p className="completion-diff warn">
          这个时长看起来不像单次任务，确认要按 {hours} 小时记录吗？记下的用时会用于校准之后的排课。
        </p>
      ) : diff !== 0 ? (
        <p className="completion-diff">
          {diff > 0 ? `比计划多用了 ${diff} 分钟` : `比计划少用了 ${-diff} 分钟`}，这个差值会用于校准之后的排课。
        </p>
      ) : null}
      <button className="primary-button full" type="button" onClick={() => onConfirm(minutes)}>
        确认完成 <Icon name="check" size={16} />
      </button>
    </div>
  );
}

function GoalEditor({ initialValue, onSave }: { initialValue: string; onSave: (value: string) => void }) {
  const [value, setValue] = useState(initialValue);
  return <div className="goal-editor"><label className="control-field"><span>目标水平</span><select value={value} onChange={(event) => setValue(event.target.value)}><option>了解核心概念</option><option>能够独立完成基础练习</option><option>能够迁移到项目实践</option></select></label><button className="primary-button full" onClick={() => onSave(value)}>保存目标</button></div>;
}

function EmptyState({ text }: { text: string }) { return <div className="empty-state"><Icon name="file" size={21} /><strong>{text}</strong><span>调整筛选条件后可以继续查看。</span></div>; }

function PlanGeneratingView() {
  return <div className="plan-generating-view"><div className="plan-generating-icon"><Icon name="spark" size={26} /></div><h1>正在重新生成计划</h1><p>正在根据最新掌握度、学习目标和你的说明，重新安排未来计划。</p><div className="plan-generating-steps"><span>分析掌握度</span><span>安排每日任务</span><span>准备诊断题与阅读材料</span></div><div className="loading-bar"><i /></div><small>此过程可能需要一些时间，请不要关闭页面。</small></div>;
}

function RegeneratePlanForm({ initialGoalLevel, onConfirm }: { initialGoalLevel: string; onConfirm: (level: typeof goalLevelOptions[number], reason: string) => void }) {
  const [level, setLevel] = useState<typeof goalLevelOptions[number]>(goalLevelOptions.includes(initialGoalLevel as typeof goalLevelOptions[number]) ? initialGoalLevel as typeof goalLevelOptions[number] : goalLevelOptions[1]);
  const [reason, setReason] = useState("");
  return <div className="regenerate-plan-form">
    <p>系统会以当前学习进度为基础，重排尚未完成的后续任务；已完成任务与学习记录保持不变。</p>
    <label className="control-field"><span>目标水平</span><select value={level} onChange={(event) => setLevel(event.target.value as typeof goalLevelOptions[number])}>{goalLevelOptions.map((option) => <option key={option}>{option}</option>)}</select></label>
    <label className="control-field"><span>调整建议（可选）</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="例如：最近时间变少，希望每天任务更轻；或想加强回归模型。" rows={4} maxLength={1000} /></label>
    <button className="primary-button full" onClick={() => onConfirm(level, reason.trim())}>调整并生成后续计划 <Icon name="arrow-right" size={16} /></button>
  </div>;
}

function Modal({ modal, onClose }: { modal: ModalState; onClose: () => void }) {
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="modal-header"><div><span className="eyebrow">操作详情</span><h2 id="modal-title">{modal.title}</h2>{modal.subtitle && <p>{modal.subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label="关闭"><Icon name="close" size={18} /></button></div><div className="modal-content">{modal.content}</div><div className="modal-actions">{modal.secondary && <button className="outline-button" onClick={modal.secondary.onClick}>{modal.secondary.label}</button>}{modal.primary && <button className="primary-button" disabled={modal.primary.disabled} onClick={modal.primary.onClick}>{modal.primary.label}</button>}</div></section></div>;
}

export { App };
