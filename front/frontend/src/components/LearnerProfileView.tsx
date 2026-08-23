import { useEffect, useState, type FormEvent } from "react";
import type { BookId } from "../data/mockData";
import { api, type LearnerProfile, type LearnerProfilePayload } from "../services/api";
import { getCurrentUserId } from "../services/session";
import { Icon } from "./Icon";

/**
 * 学习画像 = 学习前的自述。
 *
 * 这一页原来是「勾选你已经掌握的 26 个知识点，未勾选的自动记为未掌握」，
 * 那实际上是掌握度的第二条写入通道，而且会覆盖诊断测出来的结论。
 * 现在的定位：
 *   - 只收集**粗粒度自评**和背景、困惑、偏好，不再逐个知识点定性；
 *   - 掌握度只由「能力诊断 + 用户校准」产生，这一页碰不到；
 *   - 自评的作用是冷启动——还没做诊断时给排题一个先验，做过之后就退位为参考。
 */

const domains: Record<string, { value: string; label: string }> = {
  ml: { value: "machine_learning", label: "机器学习" },
  dl: { value: "deep_learning", label: "深度学习" },
};

/** 与后端 field_rules.py 的 self_assessed_level 取值一一对应，不能随便加。 */
const SELF_LEVELS: Array<{ value: string; label: string; hint: string }> = [
  { value: "none", label: "完全没接触过", hint: "从零开始，诊断会从最基础的题问起。" },
  { value: "basic", label: "看过一些概念", hint: "听过主要名词，但没动手做过。" },
  { value: "practice", label: "跟着做过练习", hint: "跟教程或课程做过例子，独立做还没把握。" },
  { value: "independent", label: "能独立解决问题", hint: "能自己完成任务，想查漏补缺。" },
];

const ACTIVITY_TYPES: Array<{ value: string; label: string }> = [
  { value: "reading", label: "阅读讲解" },
  { value: "quiz", label: "做题练习" },
  { value: "project", label: "动手项目" },
  { value: "video", label: "视频课程" },
];

const CONTENT_STYLES: Array<{ value: string; label: string }> = [
  { value: "balanced", label: "均衡" },
  { value: "concise", label: "简明扼要" },
  { value: "detailed", label: "详细展开" },
  { value: "example_first", label: "先看例子" },
];

const DIFFICULTIES: Array<{ value: string; label: string }> = [
  { value: "adaptive", label: "跟着我的水平走" },
  { value: "easy", label: "偏简单" },
  { value: "challenging", label: "偏有挑战" },
];

/**
 * 单次学习时长档位。
 * **必须与后端 modules/learner_profile/field_rules.py 的 SESSION_DURATION_CHOICES 一致**，
 * tests/test_profile_contract.py 会强制校验两边不许漂移。
 * 之前这里是个 10–120 步长 5 的滑块，选 75 分钟后端直接 field validation failed。
 */
const SESSION_DURATIONS = [15, 30, 45, 60, 90, 120];

const durationLabel = (minutes: number) => (minutes >= 60 && minutes % 60 === 0 ? `${minutes / 60} 小时` : `${minutes} 分钟`);

const FREQUENCIES: Array<{ value: string; label: string }> = [
  { value: "daily", label: "每天" },
  { value: "frequent", label: "每周三四次" },
  { value: "occasional", label: "偶尔" },
  { value: "flexible", label: "不固定" },
];

const defaultForm = (userId: string, domain: string): LearnerProfilePayload => ({
  user_id: userId,
  learning_domain: domain,
  background: "",
  self_assessed_level: "unknown",
  // 这两个列表保留在契约里（后端字段没变），但这一页不再往里写东西：
  // 逐知识点定性属于诊断的职责。
  known_knowledge_point_ids: [],
  known_knowledge_point_note: "",
  unknown_knowledge_point_ids: [],
  current_confusions: "",
  additional_requirements: "",
  preferences: {
    activity_types: ["reading", "quiz"],
    content_style: "balanced",
    difficulty: "adaptive",
    session_duration_minutes: 30,
    learning_frequency: "flexible",
  },
});

/** 后端字段名 → 界面上的说法，让报错能指到具体哪一项。 */
const FIELD_LABELS: Record<string, string> = {
  background: "当前学习背景",
  self_assessed_level: "自评水平",
  current_confusions: "当前困惑",
  additional_requirements: "其他学习要求",
  activity_types: "喜欢的学习方式",
  content_style: "讲解风格",
  difficulty: "难度倾向",
  session_duration_minutes: "单次学习时长",
  learning_frequency: "学习频率",
};

/**
 * 把后端的校验错误翻译成人话。
 * 后端在 details.issues 里给了具体是哪个字段、什么原因，
 * 之前前端只显示 message，用户看到的就是一句没用的「field validation failed」。
 */
function describeSaveError(error: unknown): string {
  const payload = error as { message?: string; details?: { issues?: Array<Record<string, unknown>> } };
  const issues = payload?.details?.issues;
  if (Array.isArray(issues) && issues.length > 0) {
    const parts = issues.slice(0, 3).map((issue) => {
      const field = String(issue.field ?? issue.name ?? "");
      const reason = String(issue.reason ?? issue.message ?? issue.rule ?? "取值不合法");
      return `${FIELD_LABELS[field] ?? (field || "某个字段")}：${reason}`;
    });
    return `保存失败 —— ${parts.join("；")}`;
  }
  return payload?.message || "保存失败，请稍后重试。";
}

const levelLabel = (value: string) => SELF_LEVELS.find((item) => item.value === value)?.label ?? "尚未填写";

export function LearnerProfileView({ bookId }: { bookId: BookId }) {
  // 用当前登录用户，不再从 URL 参数取、也不再写死 user_001——
  // 画像和诊断、今日学习必须落在同一个账号下，否则闭环是断的。
  const userId = getCurrentUserId();
  // 目录里新增的书籍尚无映射时，退回用 bookId 本身作为 learning_domain，避免页面崩溃。
  const domain = domains[bookId] ?? { value: bookId, label: bookId };

  const [form, setForm] = useState<LearnerProfilePayload>(() => defaultForm(userId, domain.value));
  const [existing, setExisting] = useState<LearnerProfile | null>(null);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setExisting(null);
    setEditing(false);
    setError("");
    setMessage("");
    setForm(defaultForm(userId, domain.value));
    api
      .getLearnerProfile(userId, domain.value)
      .then((profileResult) => {
        if (!active) return;
        if (profileResult.exists && profileResult.profile) {
          setExisting(profileResult.profile);
          setForm({ ...profileResult.profile, learning_domain: domain.value });
        }
      })
      .catch(() => active && setError("无法读取学习画像，请稍后重试。"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [domain.value, userId]);

  const update = <K extends keyof LearnerProfilePayload>(key: K, value: LearnerProfilePayload[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const updatePreference = <K extends keyof LearnerProfilePayload["preferences"]>(
    key: K,
    value: LearnerProfilePayload["preferences"][K],
  ) => setForm((current) => ({ ...current, preferences: { ...current.preferences, [key]: value } }));

  const toggleActivity = (value: string) => {
    const current = form.preferences.activity_types;
    const next = current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
    // 至少保留一种活动类型，否则计划生成没有任何可选形式。
    updatePreference("activity_types", next.length ? next : current);
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.background.trim()) {
      setError("请填写当前学习背景。");
      return;
    }
    if (form.self_assessed_level === "unknown") {
      setError("请选择一个自评水平。");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    const payload: LearnerProfilePayload = {
      ...form,
      user_id: userId,
      learning_domain: domain.value,
      background: form.background.trim(),
      // 关键改动：不再把「没勾选的知识点」写成未掌握。
      // 未测过就是未测过，掌握度等诊断来定。
      known_knowledge_point_ids: [],
      unknown_knowledge_point_ids: [],
    };
    try {
      const result = await api.saveLearnerProfile(payload);
      setExisting(result.profile ?? payload);
      setForm(result.profile ?? payload);
      setEditing(false);
      setMessage(`${domain.label}学习画像已保存。`);
    } catch (saveError) {
      setError(describeSaveError(saveError));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="page-stack narrow-page">
        <div className="card profile-loading">正在读取学习画像…</div>
      </div>
    );
  }

  if (existing && !editing) {
    return (
      <div className="page-stack narrow-page">
        <div className="page-header">
          <div>
            <span className="eyebrow">学习画像</span>
            <h1>{domain.label}画像已建立</h1>
            <p>这些信息用于个性化推荐；你的掌握度由能力诊断决定，不在这一页。</p>
          </div>
        </div>
        <div className="card profile-complete-card">
          <dl className="profile-facts">
            <div><dt>自评水平</dt><dd>{levelLabel(existing.self_assessed_level)}</dd></div>
            <div><dt>学习背景</dt><dd>{existing.background || "—"}</dd></div>
            <div><dt>当前困惑</dt><dd>{existing.current_confusions || "—"}</dd></div>
            <div><dt>单次时长</dt><dd>{durationLabel(existing.preferences.session_duration_minutes)}</dd></div>
          </dl>
          <div className="profile-note">
            <Icon name="info" size={14} />
            <span>自评只在还没做过诊断时作为起点参考。做过诊断后，掌握度以诊断结果和你的校准为准。</span>
          </div>
          <button className="outline-button" type="button" onClick={() => setEditing(true)}>
            修改画像
          </button>
        </div>
        {(error || message) && <div className="profile-message standalone">{error || message}</div>}
      </div>
    );
  }

  return (
    <div className="page-stack narrow-page">
      <div className="page-header">
        <div>
          <span className="eyebrow">学习起点 · 个性化设置</span>
          <h1>{editing ? "修改" : "建立"}{domain.label}学习画像</h1>
          <p>说说你的起点和偏好就行。具体每个知识点会不会，由能力诊断来测，这里不用逐个判断。</p>
        </div>
      </div>

      <form className="profile-form card" onSubmit={save}>
        <label className="profile-field">
          <span>当前学习背景</span>
          <textarea
            value={form.background}
            onChange={(event) => update("background", event.target.value)}
            placeholder="例如：本科学过高数和线性代数，用过 Python，没有系统学过机器学习。"
            required
          />
        </label>

        <section className="profile-section">
          <div className="profile-section-title">
            <strong>你觉得自己大概什么水平</strong>
            <span>影响诊断从哪里问起</span>
          </div>
          <div className="profile-level-list">
            {SELF_LEVELS.map((level) => (
              <button
                type="button"
                key={level.value}
                className={`profile-level ${form.self_assessed_level === level.value ? "selected" : ""}`}
                onClick={() => update("self_assessed_level", level.value)}
              >
                <span className="choice-indicator radio">{form.self_assessed_level === level.value ? "●" : ""}</span>
                <span className="choice-copy">
                  <strong>{level.label}</strong>
                  <small>{level.hint}</small>
                </span>
              </button>
            ))}
          </div>
          <div className="profile-note">
            <Icon name="info" size={14} />
            <span>这是自述，不是结论——诊断照样会测，只是会调整从哪个难度开始问。</span>
          </div>
        </section>

        <label className="profile-field">
          <span>当前困惑</span>
          <textarea
            value={form.current_confusions}
            onChange={(event) => update("current_confusions", event.target.value)}
            placeholder="例如：分不清什么时候该用分类、什么时候该用回归。"
          />
        </label>

        <label className="profile-field">
          <span>其他学习要求</span>
          <textarea
            value={form.additional_requirements}
            onChange={(event) => update("additional_requirements", event.target.value)}
            placeholder="例如：希望多一些和业务数据相关的例子。"
          />
        </label>

        <section className="profile-section">
          <div className="profile-section-title">
            <strong>学习偏好</strong>
            <span>影响任务形式和排课</span>
          </div>

          <div className="profile-prefs">
          <div className="profile-pref-row">
            <span className="profile-pref-label">喜欢的学习方式</span>
            <div className="pill-group">
              {ACTIVITY_TYPES.map((item) => (
                <button
                  type="button"
                  key={item.value}
                  className={`pill-option ${form.preferences.activity_types.includes(item.value) ? "selected" : ""}`}
                  onClick={() => toggleActivity(item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="profile-pref-row">
            <span className="profile-pref-label">讲解风格</span>
            <div className="pill-group">
              {CONTENT_STYLES.map((item) => (
                <button
                  type="button"
                  key={item.value}
                  className={`pill-option ${form.preferences.content_style === item.value ? "selected" : ""}`}
                  onClick={() => updatePreference("content_style", item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="profile-pref-row">
            <span className="profile-pref-label">难度倾向</span>
            <div className="pill-group">
              {DIFFICULTIES.map((item) => (
                <button
                  type="button"
                  key={item.value}
                  className={`pill-option ${form.preferences.difficulty === item.value ? "selected" : ""}`}
                  onClick={() => updatePreference("difficulty", item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="profile-pref-row">
            <span className="profile-pref-label">学习频率</span>
            <div className="pill-group">
              {FREQUENCIES.map((item) => (
                <button
                  type="button"
                  key={item.value}
                  className={`pill-option ${form.preferences.learning_frequency === item.value ? "selected" : ""}`}
                  onClick={() => updatePreference("learning_frequency", item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="profile-pref-row">
            <span className="profile-pref-label">单次学习时长</span>
            <div className="pill-group">
              {SESSION_DURATIONS.map((minutes) => (
                <button
                  type="button"
                  key={minutes}
                  className={`pill-option ${form.preferences.session_duration_minutes === minutes ? "selected" : ""}`}
                  onClick={() => updatePreference("session_duration_minutes", minutes)}
                >
                  {durationLabel(minutes)}
                </button>
              ))}
            </div>
            <small className="profile-pref-hint">决定单个学习任务能排多长：选 2 小时，计划里就会出现一到两小时的任务。</small>
          </div>
          </div>
        </section>

        {error && <div className="profile-message error">{error}</div>}
        {message && <div className="profile-message success">{message}</div>}
        <button className="primary-button profile-submit" type="submit" disabled={busy}>
          {busy ? "保存中…" : "保存学习画像"}
        </button>
      </form>
    </div>
  );
}
