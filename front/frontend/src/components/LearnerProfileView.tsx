import { useEffect, useMemo, useState, type FormEvent } from "react";
import type { BookId } from "../data/mockData";
import { api, type ProfileSetup, type ProfileSetupPayload } from "../services/api";

const books: Record<BookId, { id: number; label: string }> = { ml: { id: 2, label: "机器学习" }, dl: { id: 1, label: "深度学习" } };
const emptyForm = (userId: number, bookId: number): ProfileSetupPayload => ({ user_id: userId, book_id: bookId, background: "", preferred_content_style: "balanced", goal: "", aim_level: 2, daily_minutes: 30, start_date: new Date().toISOString().slice(0, 10), target_date: null });

export function LearnerProfileView({ bookId }: { bookId: BookId }) {
  const selectedBook = books[bookId];
  const queryUserId = useMemo(() => Number(new URLSearchParams(window.location.search).get("user_id") || 0), []);
  const [form, setForm] = useState(() => emptyForm(queryUserId, selectedBook.id));
  const [saved, setSaved] = useState<ProfileSetup | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setForm(emptyForm(queryUserId, selectedBook.id)); setSaved(null); setMessage(""); setError("");
    if (!queryUserId) return;
    setLoading(true);
    api.getProfileSetup(queryUserId, selectedBook.id).then((result) => {
      if (!result.profile) return;
      const profile = result.profile;
      setSaved(profile);
      setForm({ user_id: profile.user_id, book_id: profile.book_id, background: profile.background, preferred_content_style: profile.preferred_content_style || "balanced", goal: profile.goal?.goal || "", aim_level: profile.goal?.aim_level ?? 2, daily_minutes: profile.goal?.daily_minutes ?? 30, start_date: profile.goal?.start_date || null, target_date: profile.goal?.target_date || null });
    }).catch((requestError) => setError((requestError as { message?: string }).message || "无法读取用户画像。")).finally(() => setLoading(false));
  }, [queryUserId, selectedBook.id]);

  const update = <K extends keyof ProfileSetupPayload>(key: K, value: ProfileSetupPayload[K]) => setForm((current) => ({ ...current, [key]: value }));
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.user_id) { setError("请输入已存在的数字用户 ID。"); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.saveProfileSetup({ ...form, book_id: selectedBook.id, background: form.background.trim(), goal: form.goal.trim() });
      if (!result.profile) throw new Error("用户画像保存后未返回数据");
      setSaved(result.profile); setMessage("用户画像、学习目标和知识点初始掌握度已保存。");
    } catch (requestError) { setError((requestError as { message?: string }).message || "保存失败，请检查用户 ID 和数据库连接。"); } finally { setBusy(false); }
  };

  return <div className="page-stack profile-page">
    <div className="page-header"><div><span className="eyebrow">学习起点 · 用户画像</span><h1>{selectedBook.label}学习画像</h1><p>系统会先将最终目标拆解为各知识点的目标掌握度，再独立评估当前掌握度与待提升差距。</p></div></div>
    <form className="profile-form card" onSubmit={save}>
      <label className="profile-field profile-user-field"><span>用户 ID</span><input type="number" min="1" value={form.user_id || ""} onChange={(event) => update("user_id", Number(event.target.value))} placeholder="请输入已有的用户 ID" required /></label>
      <label className="profile-field"><span>学习背景</span><textarea value={form.background} onChange={(event) => update("background", event.target.value)} placeholder="例如：学过 Python，了解基础统计，但没有学习过机器学习。" required /></label>
      <label className="profile-field"><span>偏好的内容风格</span><select value={form.preferred_content_style} onChange={(event) => update("preferred_content_style", event.target.value)}><option value="concise">简洁要点</option><option value="balanced">图文均衡</option><option value="detailed">详细讲解</option><option value="example_first">示例优先</option></select></label>
      <label className="profile-field"><span>学习目标</span><textarea value={form.goal} onChange={(event) => update("goal", event.target.value)} placeholder="例如：能够独立完成分类模型训练与评估。" required /></label>
      <label className="profile-field"><span>整体目标掌握等级</span><select value={form.aim_level} onChange={(event) => update("aim_level", Number(event.target.value))}><option value={0}>0 · 没学过</option><option value={1}>1 · 入门</option><option value={2}>2 · 了解</option><option value={3}>3 · 熟练</option></select></label>
      <label className="profile-field"><span>每天可学习分钟数</span><input type="number" min="1" max="1440" value={form.daily_minutes} onChange={(event) => update("daily_minutes", Number(event.target.value))} required /></label>
      <label className="profile-field"><span>开始日期</span><input type="date" value={form.start_date || ""} onChange={(event) => update("start_date", event.target.value || null)} /></label>
      <label className="profile-field"><span>目标日期</span><input type="date" value={form.target_date || ""} onChange={(event) => update("target_date", event.target.value || null)} /></label>
      {error && <div className="profile-message error">{error}</div>}{message && <div className="profile-message success">{message}</div>}
      <button className="primary-button profile-submit" type="submit" disabled={busy || loading}>{busy ? "目标拆解与能力分析中…" : "分析并保存知识点能力"}</button>
    </form>
    {saved && <section className="card profile-complete-card"><h2>知识点目标与能力差距</h2><p>共分析 {saved.mastery.length} 个已有知识点。后续诊断结果应更新当前掌握度，而目标掌握度随学习目标调整。</p><div className="knowledge-point-picker">{saved.mastery.map((item) => <div className="profile-choice" key={item.knowledge_point_id}><span className="choice-copy"><strong>{item.name}</strong><small>当前：{Math.round(item.mastery_score * 100)}% · 目标：{Math.round(item.aim_score * 100)}% · 待提升：{Math.round(item.gap_score * 100)}% · 置信度：{Math.round(item.confidence * 100)}%</small></span></div>)}</div></section>}
  </div>;
}
