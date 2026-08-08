import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import type { BookId } from "../data/mockData";
import { api, type LearnerProfile, type LearnerProfilePayload } from "../services/api";
import { Icon } from "./Icon";

const domainConfig: Record<BookId, { value: string; label: string; description: string }> = {
  ml: { value: "machine_learning", label: "机器学习", description: "模型、数据与评估" },
  rl: { value: "reinforcement_learning", label: "强化学习", description: "状态、动作、奖励与策略" },
};

const skillOptions: Record<string, Array<[string, string]>> = {
  machine_learning: [["python", "Python"], ["numpy", "NumPy"], ["pandas", "Pandas"], ["supervised_learning", "监督学习"], ["unsupervised_learning", "无监督学习"], ["model_evaluation", "模型评估"], ["deep_learning", "深度学习"]],
  reinforcement_learning: [["python", "Python"], ["mdp", "马尔可夫决策过程"], ["reward_return", "奖励与回报"], ["value_function", "价值函数"], ["q_learning", "Q 学习"], ["exploration", "探索与利用"], ["policy_gradient", "策略梯度"]],
};

const levelOptions = [
  ["unknown", "不确定，先测评", "让诊断帮助你找到起点"],
  ["none", "完全不了解", "从核心概念和前置知识开始"],
  ["basic", "理解基础概念", "可以继续补充方法与例题"],
  ["practice", "能完成简单练习", "重点提升迁移和综合应用"],
  ["independent", "能独立应用", "适合挑战项目和复杂问题"],
];

const activityOptions = [["reading", "阅读讲解"], ["quiz", "答题练习"], ["coding", "编程练习"], ["project", "项目实践"], ["conversation", "对话问答"]];
const contentOptions = [["balanced", "适度讲解"], ["concise", "简洁总结"], ["detailed", "详细推导"], ["example_first", "先看例子"]];
const difficultyOptions = [["adaptive", "自动调整"], ["easy", "从基础开始"], ["challenging", "有挑战性"]];
const durationOptions: string[][] = [["15", "15 分钟"], ["30", "30 分钟"], ["45", "45 分钟"], ["60", "60 分钟"]];
const frequencyOptions = [["flexible", "不固定"], ["daily", "每天"], ["frequent", "每周 3～5 次"], ["occasional", "每周 1～2 次"]];

type ProfileForm = LearnerProfilePayload;

const defaultForm = (userId: string, learningDomain: string): ProfileForm => ({
  user_id: userId,
  learning_domain: learningDomain,
  background: "",
  self_assessed_level: "unknown",
  known_skill_ids: [],
  known_skill_note: "",
  current_confusions: "",
  additional_requirements: "",
  preferences: { activity_types: ["reading", "quiz"], content_style: "balanced", difficulty: "adaptive", session_duration_minutes: 30, learning_frequency: "flexible" },
});

function ChoiceCard({ selected, title, description, onClick, multi = false }: { selected: boolean; title: string; description?: string; onClick: () => void; multi?: boolean }) {
  return <button type="button" className={`profile-choice ${selected ? "selected" : ""}`} onClick={onClick}><span className={`choice-indicator ${multi ? "checkbox" : "radio"}`}>{selected && <Icon name="check" size={12} />}</span><span className="choice-copy"><strong>{title}</strong>{description && <small>{description}</small>}</span></button>;
}

export function LearnerProfileView({ bookId }: { bookId: BookId }) {
  const userId = useMemo(() => new URLSearchParams(window.location.search).get("user_id")?.trim() || "user_001", []);
  const domain = domainConfig[bookId];
  const [form, setForm] = useState<ProfileForm>(() => defaultForm(userId, domain.value));
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
    setMessage("");
    setError("");
    setForm(defaultForm(userId, domain.value));
    void api.getLearnerProfile(userId, domain.value).then((result) => {
      if (!active) return;
      if (result.exists && result.profile) {
        setExisting(result.profile);
        setForm({ ...result.profile, learning_domain: domain.value });
      }
    }).catch(() => active && setError("无法读取学习画像，请稍后重试。"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [domain.value, userId]);

  const update = <K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) => setForm((current) => ({ ...current, [key]: value }));
  const updatePreference = <K extends keyof ProfileForm["preferences"]>(key: K, value: ProfileForm["preferences"][K]) => setForm((current) => ({ ...current, preferences: { ...current.preferences, [key]: value } }));
  const toggleSkill = (skill: string) => update("known_skill_ids", form.known_skill_ids.includes(skill) ? form.known_skill_ids.filter((item) => item !== skill) : [...form.known_skill_ids, skill]);
  const toggleActivity = (activity: string) => updatePreference("activity_types", form.preferences.activity_types.includes(activity) ? form.preferences.activity_types.filter((item) => item !== activity) : [...form.preferences.activity_types, activity]);

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.background.trim()) { setError("请先填写当前背景，方便系统理解你的起点。"); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      const customSkills = form.known_skill_note.split(/[，,]/).map((item) => item.trim()).filter(Boolean);
      const payload: LearnerProfilePayload = {
        ...form,
        user_id: userId,
        learning_domain: domain.value,
        background: form.background.trim(),
        known_skill_ids: [...new Set([...form.known_skill_ids.filter((item) => !customSkills.includes(item)), ...customSkills])],
        known_skill_note: customSkills.join("，"),
      };
      const result = await api.saveLearnerProfile(payload);
      setExisting(result.profile ?? payload);
      setForm(result.profile ?? payload);
      setEditing(false);
      setMessage(`${domain.label}学习画像已保存。`);
    } catch (saveError) {
      setError((saveError as { message?: string })?.message || "保存失败，请稍后重试。");
    } finally { setBusy(false); }
  };

  const beginEdit = () => {
    if (existing) setForm({ ...existing, learning_domain: domain.value });
    setEditing(true);
    setMessage("");
    setError("");
  };

  if (loading) return <div className="page-stack narrow-page"><PageHeader title={`${domain.label}学习画像`} description="正在读取当前学习方向的画像。" /><div className="card profile-loading">正在读取学习画像…</div></div>;

  if (existing && !editing) {
    return <div className="page-stack profile-page">
      <PageHeader eyebrow="学习起点 · 个性化设置" title={`${domain.label}学习画像`} description={`该画像只用于${domain.label}，切换学习内容可查看另一份独立画像。`} action={<span className="status-pill success">已完成</span>} />
      <CompletedProfile profile={existing} domainLabel={domain.label} onEdit={beginEdit} />
      {(error || message) && <div className={`profile-message standalone ${error ? "error" : "success"}`} role="status">{error || message}</div>}
    </div>;
  }

  return <div className="page-stack profile-page">
    <PageHeader eyebrow="学习起点 · 个性化设置" title={`${editing ? "修改" : "建立"}${domain.label}学习画像`} description={`当前画像仅属于${domain.label}，不会影响其他学习方向。`} action={<span className="status-pill blue">{editing ? "正在修改" : "首次设置"}</span>} />
    <div className="profile-domain-banner"><Icon name="book" size={17} /><div><strong>{domain.label}</strong><span>{domain.description}</span></div></div>
    <form className="profile-form card" onSubmit={save}>
      <div className="profile-section profile-section-wide"><SectionTitle title="基本信息" description="这些信息用于确定诊断范围和学习上下文。" /><label className="profile-field"><span>用户 ID</span><input value={form.user_id} readOnly /></label><label className="profile-field"><span>当前背景</span><textarea value={form.background} onChange={(event) => update("background", event.target.value)} placeholder="例如：学过 Python，做过数据分析…" required /></label></div>
      <div className="profile-section"><SectionTitle title="当前自评水平" description="没有把握也没关系，后续诊断会继续校准。" /><div className="choice-list">{levelOptions.map(([value, title, description]) => <ChoiceCard key={value} selected={form.self_assessed_level === value} title={title} description={description} onClick={() => update("self_assessed_level", value)} />)}</div></div>
      <div className="profile-section"><SectionTitle title="已接触技能" description="可多选。" /><div className="choice-grid skill-grid">{skillOptions[domain.value].map(([value, title]) => <ChoiceCard key={value} selected={form.known_skill_ids.includes(value)} title={title} onClick={() => toggleSkill(value)} multi />)}</div><input className="profile-inline-input" value={form.known_skill_note} onChange={(event) => update("known_skill_note", event.target.value)} placeholder="其他技能：用逗号分隔" /></div>
      <div className="profile-section profile-section-wide"><SectionTitle title="当前困惑与学习要求" description="这部分会帮助后续推荐更贴近你的实际问题。" /><label className="profile-field"><span>当前困惑</span><textarea value={form.current_confusions} onChange={(event) => update("current_confusions", event.target.value)} placeholder="目前最想解决的问题…" /></label><label className="profile-field"><span>其他学习要求</span><textarea value={form.additional_requirements} onChange={(event) => update("additional_requirements", event.target.value)} placeholder="例如：希望多结合面试题、案例或代码…" /></label></div>
      <div className="profile-section profile-section-wide"><SectionTitle title="学习偏好" description="系统会据此安排当前方向的学习内容。" /><span className="profile-label">偏好的学习方式</span><div className="choice-grid activity-grid">{activityOptions.map(([value, title]) => <ChoiceCard key={value} selected={form.preferences.activity_types.includes(value)} title={title} onClick={() => toggleActivity(value)} multi />)}</div><div className="preference-grid"><PreferenceGroup title="内容风格" options={contentOptions} value={form.preferences.content_style} onChange={(value) => updatePreference("content_style", value)} /><PreferenceGroup title="学习难度" options={difficultyOptions} value={form.preferences.difficulty} onChange={(value) => updatePreference("difficulty", value)} /><PreferenceGroup title="单次时长" options={durationOptions} value={String(form.preferences.session_duration_minutes)} onChange={(value) => updatePreference("session_duration_minutes", Number(value))} /><PreferenceGroup title="学习频率" options={frequencyOptions} value={form.preferences.learning_frequency} onChange={(value) => updatePreference("learning_frequency", value)} /></div></div>
      {(error || message) && <div className={`profile-message ${error ? "error" : "success"}`} role="status">{error || message}</div>}
      <div className="profile-actions"><span>{editing ? "保存后将完整覆盖原画像。" : "保存后可直接进入能力诊断。"}</span><div className="profile-action-buttons">{editing && <button className="outline-button" type="button" onClick={() => setEditing(false)}>取消修改</button>}<button className="primary-button" type="submit" disabled={busy}>{busy ? "正在保存…" : editing ? "覆盖并保存画像" : "保存学习画像"}<Icon name="arrow-right" size={16} /></button></div></div>
    </form>
  </div>;
}

function CompletedProfile({ profile, domainLabel, onEdit }: { profile: LearnerProfile; domainLabel: string; onEdit: () => void }) {
  const level = levelOptions.find(([value]) => value === profile.self_assessed_level)?.[1] ?? profile.self_assessed_level;
  const skills = profile.known_skill_ids.length ? profile.known_skill_ids.map((skill) => skillOptions[profile.learning_domain]?.find(([value]) => value === skill)?.[1] ?? skill).join("、") : "暂未填写";
  const activities = profile.preferences.activity_types.map((activity) => activityOptions.find(([value]) => value === activity)?.[1] ?? activity).join("、") || "暂未填写";
  return <article className="card profile-complete-card"><div className="profile-complete-head"><div className="profile-complete-icon"><Icon name="check" size={22} /></div><div><span className="eyebrow">已完成学习画像</span><h2>{domainLabel}画像已准备好</h2><p>诊断和学习计划将读取这份画像作为个性化依据。</p></div></div><div className="profile-summary-grid"><SummaryItem label="当前背景" value={profile.background} /><SummaryItem label="自评水平" value={level} /><SummaryItem label="已接触技能" value={skills} /><SummaryItem label="偏好学习方式" value={activities} /><SummaryItem label="当前困惑" value={profile.current_confusions || "暂未填写"} /><SummaryItem label="其他学习要求" value={profile.additional_requirements || "暂未填写"} /></div><div className="profile-complete-actions"><span>修改后保存会用新的完整 JSON 覆盖当前画像。</span><button className="outline-button" type="button" onClick={onEdit}><Icon name="settings" size={15} />修改画像</button></div></article>;
}

function SummaryItem({ label, value }: { label: string; value: string }) { return <div className="profile-summary-item"><span>{label}</span><strong>{value}</strong></div>; }
function SectionTitle({ title, description }: { title: string; description: string }) { return <div className="profile-section-title"><strong>{title}</strong><span>{description}</span></div>; }
function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) { return <div className="page-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>; }
function PreferenceGroup({ title, options, value, onChange }: { title: string; options: string[][]; value: string; onChange: (value: string) => void }) { return <div className="preference-group"><span className="profile-label">{title}</span><div className="preference-options">{options.map(([optionValue, label]) => <button type="button" className={value === optionValue ? "active" : ""} key={optionValue} onClick={() => onChange(optionValue)}>{label}</button>)}</div></div>; }
