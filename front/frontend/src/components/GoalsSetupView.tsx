import { useEffect, useState } from "react";
import { Icon } from "./Icon";
import { api, type BookCatalogItem } from "../services/api";

/**
 * 选书与目标（对应闭环第 1 步）。
 * 书籍列表来自 api.getBooks()（GET /books，后端未就绪时自动回退本地目录），
 * 因此新增书籍无需修改本组件。
 */

const TARGET_LEVELS = [
  "能够复述核心概念",
  "能够独立完成基础练习",
  "能够解决进阶应用问题",
  "能够指导他人 / 应对面试",
];

const errorMessage = (error: unknown) => (error as { message?: string })?.message ?? "操作失败，请稍后重试。";

const dateInputValue = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const defaultTargetDate = () => {
  const date = new Date();
  date.setDate(date.getDate() + 30);
  return dateInputValue(date);
};

export function GoalsSetupView({
  initialBookId,
  onSaved,
  onSkip,
}: {
  initialBookId?: string;
  onSaved: (result: { bookId: string; targetLevel: string; dailyMinutes: number; targetDate: string; rescheduled?: boolean; estimatedDays?: number | null; planRefreshSuggested?: boolean }) => void;
  onSkip: () => void;
}) {
  const [catalog, setCatalog] = useState<BookCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [bookId, setBookId] = useState<string>(initialBookId ?? "");
  const [targetLevel, setTargetLevel] = useState(TARGET_LEVELS[1]);
  const [dailyMinutes, setDailyMinutes] = useState(30);
  const [targetDate, setTargetDate] = useState(defaultTargetDate);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const loadCatalog = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const result = await api.getBooks();
      setCatalog(result.books);
      const firstAvailable = result.books.find((book) => book.available !== false);
      setBookId((current) => current || (firstAvailable?.id ?? ""));
    } catch (error) {
      setLoadError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadCatalog();
  }, []);

  /**
   * 切换书籍时回填这本书已保存的目标。
   * 之前这一页永远从默认值（第二档目标、每周 5 小时）起步，
   * 用户改完保存、再打开还是默认值，看起来就像「改了没生效」。
   */
  useEffect(() => {
    if (!bookId) return;
    let active = true;
    void api.getLearnerGoal(bookId).then((result) => {
      if (!active || !result.exists || !result.goal) return;
      setTargetLevel(result.goal.targetLevel);
      setDailyMinutes(result.goal.dailyMinutes);
      setTargetDate(result.goal.targetDate ?? defaultTargetDate());
    });
    return () => { active = false; };
  }, [bookId]);

  const save = async () => {
    if (!bookId) {
      setSaveError("请选择一本书籍。");
      return;
    }
    if (!targetDate) {
      setSaveError("请选择期望完成日期。");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await api.saveLearnerGoal({ bookId, targetLevel, dailyMinutes, targetDate });
      // 后端会在每日时长或目标日期变化时自动重排在途计划的任务日期。
      onSaved({
        bookId,
        targetLevel,
        dailyMinutes,
        targetDate,
        rescheduled: saved.rescheduled,
        estimatedDays: saved.estimatedDays,
        planRefreshSuggested: saved.planRefreshSuggested,
      });
    } catch (error) {
      setSaveError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const selectedBook = catalog.find((book) => book.id === bookId);
  const stepTwoActive = Boolean(bookId);

  return (
    <div className="page-stack narrow-page">
      <div className="page-header">
        <div>
          <span className="eyebrow">开始之前，先建立学习上下文</span>
          <h1>选择书籍，设定你的学习目标</h1>
          <p>后续的能力诊断、学习计划和复习安排都会围绕这里的选择展开，之后随时可以在「学习计划」里调整。</p>
        </div>
      </div>

      <div className="onboard-steps">
        <div className={`onboard-step ${stepTwoActive ? "done" : "on"}`}>
          <span className="dot">{stepTwoActive ? <Icon name="check" size={12} /> : "1"}</span>选择书籍
        </div>
        <span className="onboard-line" />
        <div className={`onboard-step ${stepTwoActive ? "on" : ""}`}><span className="dot">2</span>目标水平</div>
        <span className="onboard-line" />
        <div className="onboard-step"><span className="dot">3</span>每日时长与日期</div>
      </div>

      <div className="card onboard-card">
        <div className="card-heading">
          <span>第一步 · 选择书籍</span>
          <small>{selectedBook ? `已选择${selectedBook.title}` : "请选择一本书籍"}</small>
        </div>

        {loading && <div className="onboard-loading">正在加载书籍目录…</div>}

        {!loading && loadError && (
          <div className="auth-message error" style={{ marginTop: 14 }}>
            <Icon name="alert" size={15} />
            <span>{loadError}</span>
            <button type="button" className="auth-link" onClick={() => void loadCatalog()}>重试</button>
          </div>
        )}

        {!loading && !loadError && catalog.length === 0 && (
          <div className="empty-state"><Icon name="file" size={21} /><strong>书籍目录为空</strong><span>后端 /books 接口返回了空列表。</span></div>
        )}

        {!loading && catalog.length > 0 && (
          <div className="book-grid">
            {catalog.map((book) => {
              const available = book.available !== false;
              return (
                <button
                  type="button"
                  key={book.id}
                  className={`book-card ${bookId === book.id ? "selected" : ""} ${available ? "" : "disabled"}`}
                  disabled={!available}
                  onClick={() => available && setBookId(book.id)}
                >
                  <span className={`book-cover ${available ? "" : "muted"}`} />
                  <strong>{book.shortTitle}</strong>
                  <small>{available ? book.subtitle : "即将上线，敬请期待"}</small>
                  <span className="book-tag">{available ? (typeof book.knowledgePointCount === "number" ? `${book.knowledgePointCount} 个知识点` : "知识点数待接口返回") : "未开放"}</span>
                </button>
              );
            })}
          </div>
        )}

        <div className="card-heading onboard-heading"><span>第二步 · 目标水平</span></div>
        <div className="pill-options">
          {TARGET_LEVELS.map((level) => (
            <button
              type="button"
              key={level}
              className={`pill-option ${targetLevel === level ? "selected" : ""}`}
              onClick={() => setTargetLevel(level)}
            >
              {level}
            </button>
          ))}
        </div>

        <div className="card-heading onboard-heading"><span>第三步 · 每天学习时长</span></div>
        <div className="hours-row">
          {/* 滑块覆盖常用区间，右侧输入框不设上限，允许填写任意强度 */}
          <input type="range" min={15} max={240} step={5} value={Math.min(dailyMinutes, 240)} onChange={(event) => setDailyMinutes(Number(event.target.value))} aria-label="每天学习时长" />
          <div className="hours-input">
            <input
              type="number"
              min={1}
              max={1440}
              value={dailyMinutes}
              onChange={(event) => setDailyMinutes(Math.max(1, Number(event.target.value) || 1))}
              aria-label="每天学习分钟数"
            />
            <span>分钟/天</span>
          </div>
        </div>
        {dailyMinutes > 480 && <p className="hours-note">每天超过 8 小时属于高强度安排，注意留出休息时间。</p>}

        <div className="card-heading onboard-heading"><span>第四步 · 期望完成日期</span></div>
        <div className="goal-date-row">
          <input
            type="date"
            min={dateInputValue(new Date())}
            value={targetDate}
            onChange={(event) => setTargetDate(event.target.value)}
            aria-label="期望完成日期"
          />
          <span>系统会结合每天可学习时间安排任务进度</span>
        </div>

        {saveError && <div className="auth-message error" style={{ marginTop: 16 }}><Icon name="alert" size={15} /><span>{saveError}</span></div>}

        <div className="onboard-foot">
          <button className="outline-button" type="button" onClick={onSkip}>跳过，先随便看看</button>
          <button className="primary-button" type="button" onClick={() => void save()} disabled={saving || !bookId}>
            {saving ? "保存中…" : "保存目标，开始能力诊断"}
            <Icon name="arrow-right" size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
