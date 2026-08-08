import { useMemo, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./components/Icon";
import { LearnerProfileView } from "./components/LearnerProfileView";
import { api, type ApiError, type DiagnosticResult } from "./services/api";
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
type ModalState = {
  title: string;
  subtitle?: string;
  content: ReactNode;
  primary?: { label: string; onClick: () => void; disabled?: boolean };
  secondary?: { label: string; onClick: () => void };
};

const navigation: Array<{ key: NavKey; label: string; icon: IconName }> = [
  { key: "today", label: "今日学习", icon: "home" },
  { key: "profile", label: "学习画像", icon: "user" },
  { key: "diagnostic", label: "能力诊断", icon: "target" },
  { key: "plan", label: "学习计划", icon: "calendar" },
  { key: "records", label: "学习记录", icon: "chart" },
  { key: "qa", label: "资料问答", icon: "chat" },
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
  const [bookId, setBookId] = useState<BookId>(books[0].id);
  const [toast, setToast] = useState<Toast>(null);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [taskStates, setTaskStates] = useState<Record<string, TaskStatus>>({});
  const [planTab, setPlanTab] = useState<"overview" | "knowledge">("overview");
  const [goalLevel, setGoalLevel] = useState("能够独立完成基础练习");

  const [diagnosticStage, setDiagnosticStage] = useState<"question" | "result">("question");
  const [diagnosticIndex, setDiagnosticIndex] = useState(0);
  const [diagnosticAnswers, setDiagnosticAnswers] = useState<Record<string, string>>({});
  const [diagnosticQuestions, setDiagnosticQuestions] = useState<DiagnosticQuestion[]>(() => getBookContent(books[0].id).questions);
  const [skippedQuestions, setSkippedQuestions] = useState<string[]>([]);
  const [diagnosticPaused, setDiagnosticPaused] = useState(false);
  const [diagnosticBusy, setDiagnosticBusy] = useState(false);
  const [diagnosticId, setDiagnosticId] = useState(`demo-${bookId}-diagnostic`);
  const [diagnosticResult, setDiagnosticResult] = useState<DiagnosticResult | null>(null);
  const [calibration, setCalibration] = useState<Calibration | null>(null);
  const [calibrationReason, setCalibrationReason] = useState("");

  const [recordFilter, setRecordFilter] = useState<"all" | RecordItem["category"]>("all");
  const [qaInput, setQaInput] = useState("");
  const [qaBusy, setQaBusy] = useState(false);
  const [qaError, setQaError] = useState<string | null>(null);
  const [qaMessages, setQaMessages] = useState<QaMessage[]>(() => buildMessages(getBookContent(books[0].id)));

  const currentBook = useMemo(() => books.find((book) => book.id === bookId) ?? books[0], [bookId]);
  const content = useMemo(() => getBookContent(bookId), [bookId]);
  const currentTasks = useMemo(
    () => content.planTasks.map((task) => ({ ...task, status: taskStates[task.id] ?? task.status })),
    [content, taskStates],
  );
  const currentQuestion = diagnosticQuestions[diagnosticIndex] ?? diagnosticQuestions[0];

  const showToast = (title: string, message: string) => {
    setToast({ title, message });
    window.setTimeout(() => setToast(null), 3200);
  };

  const closeModal = () => setModal(null);

  const resetBookState = (nextBookId: BookId) => {
    setBookId(nextBookId);
    setTaskStates({});
    setPlanTab("overview");
    setDiagnosticStage("question");
    setDiagnosticIndex(0);
    setDiagnosticAnswers({});
    setDiagnosticQuestions(getBookContent(nextBookId).questions);
    setSkippedQuestions([]);
    setDiagnosticPaused(false);
    setDiagnosticId(`demo-${nextBookId}-diagnostic`);
    setDiagnosticResult(null);
    setCalibration(null);
    setCalibrationReason("");
    setQaMessages(buildMessages(getBookContent(nextBookId)));
    setQaError(null);
    showToast("已切换学习内容", `${getBookContent(nextBookId).goal}的页面内容已更新。`);
  };

  const goTo = (key: NavKey) => setActiveNav(key);

  const startDiagnostic = async () => {
    setActiveNav("diagnostic");
    setDiagnosticStage("question");
    setDiagnosticIndex(0);
    setDiagnosticAnswers({});
    setSkippedQuestions([]);
    setDiagnosticPaused(false);
    setDiagnosticBusy(true);
    try {
      const result = await api.startDiagnostic(bookId, content.goal);
      setDiagnosticId(result.diagnosticId);
      if (result.questions.length > 0) setDiagnosticQuestions(result.questions);
      showToast("诊断已开始", `共 ${content.questions.length} 道题，答案会逐题保存。`);
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
    const answer = diagnosticAnswers[currentQuestion.id];
    if (!answer) {
      showToast("还没有提交答案", "请选择一个选项后继续诊断。 ");
      return;
    }
    void advanceDiagnostic(currentQuestion, answer);
  };

  const skipDiagnostic = () => {
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
      await api.submitCalibration({ diagnosticId, level: calibration, reason: calibrationReason });
      await api.generatePlan({ bookId, goal: content.goal });
      setActiveNav("plan");
      showToast("校准已提交", "学习计划已根据新的校准信息更新。 ");
    } catch (error) {
      showToast("校准提交失败", errorMessage(error));
    } finally {
      setDiagnosticBusy(false);
    }
  };

  const updateTask = async (task: LearningTask) => {
    const currentStatus = taskStates[task.id] ?? task.status;
    const nextStatus: TaskStatus = currentStatus === "completed" ? "completed" : currentStatus === "in_progress" ? "completed" : "in_progress";
    setTaskStates((states) => ({ ...states, [task.id]: nextStatus }));
    try {
      await api.writeLearningEvent({ taskId: task.id, eventType: nextStatus === "completed" ? "task_completed" : "task_started", status: nextStatus });
      showToast(nextStatus === "completed" ? "任务已完成" : "任务已开始", nextStatus === "completed" ? "下一项学习任务已经准备好。" : "完成后可以继续更新学习进度。 ");
    } catch (error) {
      setTaskStates((states) => ({ ...states, [task.id]: currentStatus }));
      showToast("任务更新失败", errorMessage(error));
    }
  };

  const openTask = (task: LearningTask) => {
    const status = taskStates[task.id] ?? task.status;
    setModal({
      title: task.title,
      subtitle: `${task.type} · ${task.minutes} 分钟 · ${statusLabels[status]}`,
      content: <div className="task-detail"><p>{task.description}</p><div className="detail-grid"><span>推荐理由</span><strong>{task.reason}</strong><span>关联目标</span><strong>{content.goal}</strong></div></div>,
      secondary: { label: "关闭", onClick: closeModal },
      primary: status === "completed" ? undefined : { label: status === "in_progress" ? "完成任务" : "开始任务", onClick: () => { closeModal(); void updateTask(task); } },
    });
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
    content: <div className="dialog-list"><div className="dialog-list-item"><Icon name="target" size={17} /><div><strong>作答表现</strong><p>{diagnosticResult?.evidence ?? "当前诊断题的作答结果和关联知识点表现。"}</p></div></div><div className="dialog-list-item"><Icon name="clock" size={17} /><div><strong>判断时间</strong><p>本次诊断完成后生成，后端接入后展示实际时间。</p></div></div><div className="dialog-list-item"><Icon name="file" size={17} /><div><strong>关联范围</strong><p>{content.goal}及其前置知识点。</p></div></div></div>,
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

  const openSource = (source: Source) => setModal({
    title: "资料来源",
    subtitle: `${source.type} · ${source.title} · ${source.location}`,
    content: <div className="source-preview"><span className="source-type">{source.type}</span><h3>{source.title}</h3><p>{source.excerpt}</p><div className="source-location"><Icon name="file" size={15} />定位：{source.location}</div></div>,
    secondary: { label: "关闭", onClick: closeModal },
  });

  const askQuestion = async () => {
    const question = qaInput.trim();
    if (!question || qaBusy) {
      if (!question) showToast("请输入问题", "输入问题后再发送。 ");
      return;
    }
    setQaInput("");
    setQaError(null);
    setQaMessages((messages) => [...messages, { role: "user", text: question }]);
    setQaBusy(true);
    try {
      const result = await api.askQuestion({ bookId, question, sources: content.sources });
      setQaMessages((messages) => [...messages, { role: "assistant", text: question.includes("过拟合") ? content.qaAnswer : result.answer, citations: result.citations }]);
    } catch (error) {
      setQaError(errorMessage(error));
    } finally {
      setQaBusy(false);
    }
  };

  const filteredRecords = content.records.filter((record) => recordFilter === "all" || record.category === recordFilter);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup"><div className="brand-mark"><Icon name="book-open" size={22} /></div><div><strong>自适应伴学智能体</strong><span>学习闭环</span></div></div>
        <nav className="main-nav" aria-label="主导航">{navigation.map((item) => <button className={`nav-item ${activeNav === item.key ? "active" : ""}`} key={item.key} onClick={() => goTo(item.key)}><Icon name={item.icon} size={19} /><span>{item.label}</span></button>)}</nav>
        <div className="sidebar-bottom"><button className="nav-item" onClick={() => setModal({ title: "设置", subtitle: "用户偏好与学习提醒", content: <div className="dialog-list"><div className="dialog-list-item"><Icon name="clock" size={17} /><div><strong>学习时间</strong><p>后端接入后可保存每周学习时长和提醒时间。</p></div></div><div className="dialog-list-item"><Icon name="target" size={17} /><div><strong>目标偏好</strong><p>可从学习计划页面调整当前目标水平。</p></div></div></div>, secondary: { label: "关闭", onClick: closeModal } })}><Icon name="settings" size={19} /><span>设置</span></button><button className="nav-item" onClick={() => setModal({ title: "帮助中心", subtitle: "自适应伴学智能体使用说明", content: <div className="dialog-list"><div className="dialog-list-item"><Icon name="book" size={17} /><div><strong>先选择学习内容</strong><p>当前支持机器学习和强化学习，后续可以继续增加书籍。</p></div></div><div className="dialog-list-item"><Icon name="target" size={17} /><div><strong>再完成能力诊断</strong><p>诊断结果和用户校准会共同影响学习计划。</p></div></div></div>, secondary: { label: "关闭", onClick: closeModal } })}><Icon name="help" size={19} /><span>帮助</span></button></div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div className="mobile-brand"><div className="brand-mark"><Icon name="book-open" size={20} /></div></div><div className="topbar-context"><span className="context-label">当前学习内容</span><label className="book-select"><Icon name="book" size={18} /><select value={bookId} onChange={(event) => resetBookState(event.target.value as BookId)} aria-label="选择当前学习内容">{books.map((book) => <option key={book.id} value={book.id}>{book.title}</option>)}</select><Icon name="chevron-down" size={15} /></label></div></header>
        {activeNav === "today" && <TodayView book={currentBook} content={content} tasks={currentTasks} goTo={goTo} startDiagnostic={startDiagnostic} onOpenTask={openTask} onOpenKnowledge={openKnowledgeDetail} onOpenRecords={() => goTo("records")} />}
        {activeNav === "profile" && <LearnerProfileView bookId={bookId} />}
        {activeNav === "diagnostic" && <DiagnosticView questions={content.questions} index={diagnosticIndex} answers={diagnosticAnswers} skippedQuestions={skippedQuestions} paused={diagnosticPaused} busy={diagnosticBusy} stage={diagnosticStage} result={diagnosticResult} calibration={calibration} calibrationReason={calibrationReason} setAnswer={(id) => setDiagnosticAnswers((answers) => ({ ...answers, [currentQuestion.id]: id }))} onPrevious={() => setDiagnosticIndex((index) => Math.max(0, index - 1))} onSubmit={submitDiagnostic} onSkip={skipDiagnostic} onPause={() => setDiagnosticPaused(true)} onResume={resumeDiagnostic} onCalibration={setCalibration} onReason={setCalibrationReason} onEvidence={openEvidence} onCalibrationSubmit={submitCalibration} />}
        {activeNav === "plan" && <PlanView book={currentBook} goal={content.goal} goalLevel={goalLevel} tasks={currentTasks} tab={planTab} setTab={setPlanTab} onOpenTask={openTask} onAdjustGoal={openGoalEditor} onOpenSource={openSource} />}
        {activeNav === "records" && <RecordsView records={filteredRecords} filter={recordFilter} setFilter={setRecordFilter} onOpenRecord={openRecord} onReview={() => startDiagnostic()} />}
        {activeNav === "qa" && <QaView book={currentBook} sources={content.sources} messages={qaMessages} value={qaInput} busy={qaBusy} error={qaError} onChange={setQaInput} onAsk={askQuestion} onNew={() => { setQaMessages(buildMessages(content)); setQaError(null); showToast("已新建对话", "当前对话已经清空。 "); }} onOpenSource={openSource} onAddPlan={() => showToast("已加入计划", "后端接入后会创建对应学习任务。 ")} />}
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

function TodayView({ book, content, tasks, goTo, startDiagnostic, onOpenTask, onOpenKnowledge, onOpenRecords }: { book: Book; content: ReturnType<typeof getBookContent>; tasks: LearningTask[]; goTo: (key: NavKey) => void; startDiagnostic: () => void; onOpenTask: (task: LearningTask) => void; onOpenKnowledge: () => void; onOpenRecords: () => void }) {
  const completed = tasks.filter((task) => task.status === "completed").length;
  return <div className="page-stack"><PageHeader eyebrow="持续学习，循序提升" title="今日学习" description={`${book.title} · ${book.subtitle} · 本周已学习 6.2 小时`} /><section className="stat-grid"><article className="card progress-card"><div className="card-heading"><span>本周进度</span><Icon name="more" size={18} /></div><div className="progress-content"><div className="ring-progress"><span>68<small>%</small></span></div><div className="progress-facts"><div><strong>{completed + 9}/18</strong><span>已完成任务</span></div><div><strong>6.2 h</strong><span>学习时长</span></div><div><strong>74%</strong><span>正确率</span></div></div></div><div className="mini-bars" aria-label="本周学习时长趋势">{[35, 52, 42, 71, 58, 84, 48].map((height, index) => <i style={{ height: `${height}%` }} key={index} />)}</div><div className="week-labels"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div></article><article className="card recommend-card"><div className="card-heading"><span>今日推荐任务</span><span className="status-pill success">最需要提升</span></div><h2>{content.recommendation.title}</h2><div className="task-meta"><span><Icon name="clock" size={14} />预计用时 {content.recommendation.minutes} 分钟</span><span>难度 {content.recommendation.difficulty}</span></div><button className="primary-button" onClick={() => goTo("plan")}>开始学习 <Icon name="arrow-right" size={16} /></button><div className="recommend-reason"><strong>为什么推荐</strong><p>{content.recommendation.reason}</p><button onClick={startDiagnostic}>开始诊断 <Icon name="arrow-up-right" size={14} /></button></div></article><article className="card continue-card"><div className="card-heading"><span>继续学习</span><Icon name="spark" size={18} /></div><div className="target-icon"><Icon name="target" size={23} /></div><h2>{content.goal}</h2><p>上次学习到：{content.lastLearned}</p><button className="outline-button" onClick={() => goTo("plan")}>继续学习</button><button className="text-button" onClick={onOpenRecords}>查看学习记录 <Icon name="arrow-right" size={14} /></button></article></section><section className="dashboard-grid"><article className="card knowledge-card"><div className="card-heading"><div><span>能力图谱</span><small>当前学习目标关联的知识点</small></div><div className="legend"><span><i className="dot green" />掌握良好</span><span><i className="dot blue" />正在学习</span><span><i className="dot amber" />薄弱</span></div></div><div className="knowledge-map"><div className="knowledge-core">{content.goal}</div>{content.nodes.map((node) => <div className={`knowledge-node ${node.tone}`} style={{ left: node.left, top: node.top }} key={node.label}>{node.label}</div>)}</div><button className="secondary-button" onClick={onOpenKnowledge}>查看图谱详情 <Icon name="arrow-right" size={15} /></button></article><article className="card task-card"><div className="card-heading"><span>今日任务</span><span className="completion">{completed}/{tasks.length} 已完成</span></div><div className="task-list">{tasks.map((task) => <TaskRow task={task} key={task.id} onOpen={() => onOpenTask(task)} />)}</div><button className="secondary-button full" onClick={() => goTo("plan")}>查看完整计划 <Icon name="arrow-right" size={15} /></button></article></section></div>;
}

function DiagnosticView({ questions, index, answers, skippedQuestions, paused, busy, stage, result, calibration, calibrationReason, setAnswer, onPrevious, onSubmit, onSkip, onPause, onResume, onCalibration, onReason, onEvidence, onCalibrationSubmit }: { questions: DiagnosticQuestion[]; index: number; answers: Record<string, string>; skippedQuestions: string[]; paused: boolean; busy: boolean; stage: "question" | "result"; result: DiagnosticResult | null; calibration: Calibration | null; calibrationReason: string; setAnswer: (id: string) => void; onPrevious: () => void; onSubmit: () => void; onSkip: () => void; onPause: () => void; onResume: () => void; onCalibration: (value: Calibration) => void; onReason: (value: string) => void; onEvidence: () => void; onCalibrationSubmit: () => void }) {
  if (stage === "result") return <DiagnosticResult result={result} calibration={calibration} reason={calibrationReason} busy={busy} onCalibration={onCalibration} onReason={onReason} onEvidence={onEvidence} onSubmit={onCalibrationSubmit} />;
  const question = questions[index];
  if (paused) return <div className="page-stack narrow-page"><PageHeader eyebrow="诊断已暂停" title="稍后继续诊断" description="已保存的答案不会丢失，回来后可以从当前题目继续。" /><article className="card pause-card"><div className="pause-icon"><Icon name="clock" size={25} /></div><h2>当前进度：第 {index + 1} / {questions.length} 题</h2><p>已完成 {Object.keys(answers).length} 题，跳过 {skippedQuestions.length} 题。</p><button className="primary-button" onClick={onResume}>继续诊断 <Icon name="arrow-right" size={16} /></button></article></div>;
  return <div className="page-stack narrow-page"><PageHeader eyebrow={`诊断会话 · 第 ${index + 1}/${questions.length} 题`} title="能力诊断" description="用少量题目了解当前基础，结果会生成可解释的学习建议。" action={<button className="text-button" onClick={onPause}><Icon name="clock" size={15} />暂时离开</button>} /><div className="diagnostic-progress"><span style={{ width: `${((index + 1) / questions.length) * 100}%` }} /><b>{index + 1} / {questions.length}</b></div><article className="card question-card"><div className="question-top"><span className="question-type">单选题</span><span className="question-tag">{question.tag}</span></div><h2>{question.title}</h2><div className="answer-list">{question.options.map((option) => <button className={`answer-option ${answers[question.id] === option.id ? "selected" : ""}`} key={option.id} onClick={() => setAnswer(option.id)}><span className="option-key">{option.id}</span><span>{option.text}</span>{answers[question.id] === option.id && <Icon name="check-circle" size={18} />}</button>)}</div><div className="question-actions"><div className="question-left-actions"><button className="text-button" disabled={index === 0 || busy} onClick={onPrevious}>上一题</button><button className="text-button" disabled={busy} onClick={onSkip}>跳过</button></div><button className="primary-button" disabled={busy} onClick={onSubmit}>{busy ? "正在保存…" : index === questions.length - 1 ? "提交诊断" : "提交并继续"} <Icon name="arrow-right" size={16} /></button></div></article><div className="info-banner"><Icon name="info" size={18} /><span>答案会逐题保存，诊断完成后可以查看判断依据。{skippedQuestions.length > 0 && ` 已跳过 ${skippedQuestions.length} 题。`}</span></div></div>;
}

function DiagnosticResult({ result, calibration, reason, busy, onCalibration, onReason, onEvidence, onSubmit }: { result: DiagnosticResult | null; calibration: Calibration | null; reason: string; busy: boolean; onCalibration: (value: Calibration) => void; onReason: (value: string) => void; onEvidence: () => void; onSubmit: () => void }) {
  return <div className="page-stack"><PageHeader eyebrow="诊断完成" title="测评结果与校准" description="AI 判断和你的自我判断会分别保存，共同影响下一轮学习计划。" action={<span className="status-pill success"><Icon name="check" size={14} />已完成</span>} /><section className="result-grid"><article className="card result-card"><div className="card-heading"><span>AI 评估结果</span><Icon name="spark" size={18} /></div><div className="result-level"><span>能力水平</span><strong>{result?.level ?? "中等偏上"}</strong></div><div className="level-scale"><i style={{ left: "60%" }} /><span>薄弱</span><span>中等</span><span>优秀</span></div><div className="result-metrics"><div><strong>{result?.accuracy ?? "75%"}</strong><span>正确率</span></div><div><strong>{result?.confidence ?? "高"}</strong><span>置信度</span></div></div><div className="evidence-summary"><Icon name="file" size={16} /><div><strong>主要依据</strong><p>{result?.evidence ?? "题目作答结果以及关联知识点表现。"}</p></div></div><button className="secondary-button full" onClick={onEvidence}>查看全部依据 <Icon name="arrow-right" size={15} /></button></article><article className="card result-card calibration-card"><div className="card-heading"><span>用户校准</span><span className="status-pill blue">独立记录</span></div><p className="calibration-intro">你认为自己的真实水平是：</p><div className="calibration-options">{([ ["lower", "低于判断", "我还不太熟悉"], ["same", "基本符合", "这个判断比较准确"], ["higher", "高于判断", "我在其他场景用过"] ] as const).map(([key, title, description]) => <button className={`calibration-option ${calibration === key ? "selected" : ""}`} key={key} onClick={() => onCalibration(key)}><span className="radio-dot" /><div><strong>{title}</strong><small>{description}</small></div>{calibration === key && <Icon name="check-circle" size={18} />}</button>)}</div><label className="reason-input"><span>补充原因（可选）</span><textarea value={reason} onChange={(event) => onReason(event.target.value)} placeholder="例如：我在项目中使用过类似方法。" rows={3} /></label><button className="primary-button full" disabled={!calibration || busy} onClick={onSubmit}>{busy ? "正在提交…" : "提交校准并生成计划"} <Icon name="arrow-right" size={16} /></button></article></section></div>;
}

function PlanView({ book, goal, goalLevel, tasks, tab, setTab, onOpenTask, onAdjustGoal, onOpenSource }: { book: Book; goal: string; goalLevel: string; tasks: LearningTask[]; tab: "overview" | "knowledge"; setTab: (tab: "overview" | "knowledge") => void; onOpenTask: (task: LearningTask) => void; onAdjustGoal: () => void; onOpenSource: (source: Source) => void }) {
  const completed = tasks.filter((task) => task.status === "completed").length;
  return <div className="page-stack"><PageHeader eyebrow="学习闭环 · 目标到任务" title="学习计划" description={`${book.title} · 系统会根据目标、诊断结果、用户校准和时间约束排列任务。`} action={<button className="outline-button" onClick={onAdjustGoal}>调整目标</button>} /><section className="plan-layout"><article className="card plan-summary"><span className="section-label">计划目标</span><h2>{goal}</h2><p>{goalLevel}</p><div className="ring-progress small"><span>{Math.round((completed / tasks.length) * 100)}<small>%</small></span></div><button className="secondary-button full" onClick={onAdjustGoal}>调整目标</button></article><article className="card plan-table-card"><div className="plan-tabs"><button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>计划总览</button><button className={tab === "knowledge" ? "active" : ""} onClick={() => setTab("knowledge")}>知识点列表</button></div>{tab === "overview" ? <><div className="plan-table-head"><span>任务</span><span>状态</span><span>预计用时</span><span>推荐理由</span></div><div className="plan-table">{tasks.map((task) => <button className="plan-row plan-row-button" key={task.id} onClick={() => onOpenTask(task)}><div className="plan-task"><span className={`timeline-dot ${task.status}`} /><div><strong>{task.title}</strong><small>{task.type}</small></div></div><span className={`status-pill ${task.status}`}>{statusLabels[task.status]}</span><span className="duration">{task.minutes ? `${task.minutes} 分钟` : "—"}</span><span className="reason">{task.reason}</span></button>)}</div></> : <div className="knowledge-list">{tasks.map((task) => <button className="knowledge-list-item" key={task.id} onClick={() => onOpenTask(task)}><span className="task-status in_progress"><Icon name="target" size={13} /></span><div><strong>{task.title}</strong><small>{task.description}</small></div><Icon name="chevron-right" size={16} /></button>)}</div>}</article></section><section className="plan-bottom-grid"><article className="card advice-card"><div className="card-heading"><span>学习建议</span><Icon name="spark" size={18} /></div><p>今天建议先完成{tasks.find((task) => task.status === "in_progress")?.title ?? tasks[0].title}，再进行一次短复测。</p><ul><li>保持连续学习，减少间隔过长</li><li>完成后进行 1 次短复测</li></ul></article><article className="card resources-card"><div className="card-heading"><span>推荐资料</span><Icon name="file" size={18} /></div><button onClick={() => onOpenSource({ id: "plan-book", type: "教材", title: `${book.shortTitle} · 重点章节`, location: "第 3 章", excerpt: `这份资料用于支持“${goal}”的学习目标。` })}><Icon name="book" size={16} /><span>教材 · 重点章节</span><Icon name="arrow-up-right" size={14} /></button><button onClick={() => onOpenSource({ id: "plan-note", type: "讲义", title: `${book.shortTitle} · 复习讲义`, location: "第 2 节", excerpt: "建议在完成练习后回看这份讲义，确认关键概念之间的关系。" })}><Icon name="file" size={16} /><span>讲义 · 复习重点</span><Icon name="arrow-up-right" size={14} /></button></article></section></div>;
}

function RecordsView({ records, filter, setFilter, onOpenRecord, onReview }: { records: RecordItem[]; filter: "all" | RecordItem["category"]; setFilter: (filter: "all" | RecordItem["category"]) => void; onOpenRecord: (record: RecordItem) => void; onReview: () => void }) {
  return <div className="page-stack"><PageHeader eyebrow="学习事件 · 可追溯" title="学习记录" description="查看作答、任务完成、校准和复测安排的历史记录。" action={<label className="filter-select"><Icon name="filter" size={15} /><select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)} aria-label="筛选学习记录"><option value="all">全部记录</option><option value="task">学习任务</option><option value="diagnostic">诊断校准</option><option value="qa">资料问答</option></select></label>} /><section className="records-layout"><article className="card record-timeline"><div className="card-heading"><span>最近活动</span><span className="completion">本周 {records.length} 个筛选结果</span></div>{records.length === 0 ? <EmptyState text="暂时没有符合条件的记录" /> : records.map((item) => <div className="record-item" key={item.id}><div className={`record-icon ${item.tone}`}><Icon name={item.icon} size={16} /></div><div className="record-copy"><strong>{item.title}</strong><p>{item.description}</p><span>{item.time}</span></div><button className="icon-button" onClick={() => onOpenRecord(item)} aria-label="查看记录详情"><Icon name="chevron-right" size={17} /></button></div>)}</article><article className="card review-card"><div className="card-heading"><span>待复测</span><span className="status-pill warning">2 个知识点</span></div><p>建议在最近学习后复测，确认能力状态是否稳定。</p><div className="review-item"><div><strong>当前薄弱知识点</strong><span>建议在今天复测</span></div><button className="secondary-button" onClick={onReview}>去复测</button></div><div className="review-item"><div><strong>复测安排</strong><span>下一次复测将在 2 天后</span></div><button className="text-button" onClick={() => setFilter("diagnostic")}>查看诊断记录</button></div></article></section></div>;
}

function QaView({ book, sources, messages, value, busy, error, onChange, onAsk, onNew, onOpenSource, onAddPlan }: { book: Book; sources: Source[]; messages: QaMessage[]; value: string; busy: boolean; error: string | null; onChange: (value: string) => void; onAsk: () => void; onNew: () => void; onOpenSource: (source: Source) => void; onAddPlan: () => void }) {
  return <div className="page-stack"><PageHeader eyebrow="资料驱动 · 保留引用" title="资料问答" description="围绕当前学习内容和学习目标提问，回答会保留资料出处。" action={<button className="outline-button" onClick={onNew}>新建对话 <Icon name="plus" size={15} /></button>} /><section className="qa-layout"><article className="card conversation-card"><div className="conversation-head"><div><span className="section-label">当前范围</span><strong>{book.title} · {book.subtitle}</strong></div><span className="status-pill blue">已绑定知识点</span></div><div className="message-list">{messages.map((message, index) => <div className={`message ${message.role}`} key={`${message.role}-${index}`}><span className="message-avatar">{message.role === "assistant" ? "✦" : "我"}</span><div><p>{message.text}</p>{message.role === "assistant" && <div className="citation-row">{(message.citations ?? sources).map((source) => <button key={source.id} onClick={() => onOpenSource(source)}><Icon name="file" size={14} /><span><strong>{source.type} · {source.title}</strong><small>{source.location}</small></span><Icon name="chevron-right" size={14} /></button>)}</div>}</div></div>)}{busy && <div className="message assistant"><span className="message-avatar">✦</span><div className="typing-state">正在查找相关资料…</div></div>}{error && <div className="inline-error" role="alert"><Icon name="info" size={16} /><span>{error}</span><button onClick={onAsk}>重新发送</button></div>}</div><div className="chat-composer"><textarea value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onAsk(); } }} placeholder="继续提问（Shift + Enter 换行）" rows={2} /><button className="send-button" onClick={onAsk} disabled={busy} aria-label="发送问题"><Icon name="send" size={17} /></button></div><div className="suggestion-row"><button onClick={() => onChange("这个概念如何举例？")}>这个概念如何举例？</button><button onClick={() => onChange("需要哪些前置知识？")}>需要哪些前置知识？</button></div></article><aside className="card source-card"><div className="card-heading"><span>来源详情</span><Icon name="info" size={17} /></div>{sources.map((source) => <div className="source-block" key={source.id}><span className="source-type">{source.type}</span><strong>{source.title}</strong><p>{source.excerpt}</p><button onClick={() => onOpenSource(source)}>打开来源 <Icon name="arrow-up-right" size={14} /></button></div>)}<button className="secondary-button full" onClick={onAddPlan}>加入学习计划 <Icon name="plus" size={15} /></button></aside></section></div>;
}

function TaskRow({ task, onOpen }: { task: LearningTask; onOpen: () => void }) {
  return <button className="task-row task-row-button" onClick={onOpen}><span className={`task-status ${task.status}`}>{task.status === "completed" ? <Icon name="check" size={13} /> : task.status === "in_progress" ? <i /> : <span />}</span><div><strong>{task.title}</strong><small>{task.type}</small></div><span className="task-duration">{task.minutes} 分钟</span><span className="task-state">{statusLabels[task.status]}</span></button>;
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
