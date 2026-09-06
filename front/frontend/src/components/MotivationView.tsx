import { useEffect, useMemo, useState } from "react";
import { Icon } from "./Icon";
import { practiceApi, type PracticeAchievement, type PracticeStats } from "../services/api";
import { getCurrentUserId } from "../services/session";
import { PracticeView } from "./PracticeView";
import "./motivation.css";

type RankingKey = "score" | "answers" | "accuracy" | "duration";
type RangeKey = "week" | "month";

type Learner = {
  name: string;
  avatar: string;
  tone: string;
  answers: number;
  accuracy: number;
  minutes: number;
  score: number;
  streak: number;
  isMe?: boolean;
};

type MotivationCache = { savedAt: number; learners: Learner[]; weeklyStats: PracticeStats };

const motivationCacheKey = () => `study-companion:motivation:${getCurrentUserId()}`;

function readMotivationCache(): MotivationCache | null {
  try {
    const raw = window.sessionStorage.getItem(motivationCacheKey());
    const cached = raw ? JSON.parse(raw) as MotivationCache : null;
    // 只复用当前浏览器会话中 5 分钟内的真实接口结果，不会长期展示过期排行。
    return cached && Date.now() - cached.savedAt < 5 * 60_000 ? cached : null;
  } catch { return null; }
}

function writeMotivationCache(patch: Partial<MotivationCache>) {
  try {
    const previous = readMotivationCache();
    window.sessionStorage.setItem(motivationCacheKey(), JSON.stringify({
      savedAt: Date.now(),
      learners: patch.learners ?? previous?.learners ?? [],
      weeklyStats: patch.weeklyStats ?? previous?.weeklyStats ?? { answerCount: 0, correctCount: 0, accuracy: 0 },
    }));
  } catch { /* 缓存不可用时仍正常走网络请求。 */ }
}

const rankingTabs: Array<{ key: RankingKey; label: string; hint: string }> = [
  { key: "score", label: "综合成长", hint: "答题、准确率与学习投入的综合表现" },
  { key: "answers", label: "无限答题", hint: "按有效答题数量排名" },
  { key: "accuracy", label: "正确率", hint: "至少完成 50 题后参与排名" },
  { key: "duration", label: "学习时长", hint: "按有效专注学习时长排名" },
];

const valueFor = (learner: Learner, key: RankingKey) => learner[key === "duration" ? "minutes" : key];

function metricText(learner: Learner, key: RankingKey) {
  if (key === "accuracy") return `${learner.accuracy}%`;
  if (key === "duration") return `${Math.floor(learner.minutes / 60)}h ${learner.minutes % 60}m`;
  if (key === "answers") return `${learner.answers} 题`;
  return `${learner.score.toLocaleString()} XP`;
}

export function MotivationView({ nickname, bookId, bookTitle }: { nickname: string; bookId: string; bookTitle: string }) {
  const cachedMotivation = readMotivationCache();
  const [ranking, setRanking] = useState<RankingKey>("score");
  const [range, setRange] = useState<RangeKey>("week");
  const [badgeFilter, setBadgeFilter] = useState<"all" | "earned">("all");
  const [practiceLearners, setPracticeLearners] = useState<Learner[]>(() => cachedMotivation?.learners ?? []);
  const [showPractice, setShowPractice] = useState(false);
  const [showScoreRules, setShowScoreRules] = useState(false);
  const [weeklyStats, setWeeklyStats] = useState<PracticeStats>(() => cachedMotivation?.weeklyStats ?? { answerCount: 0, correctCount: 0, accuracy: 0 });
  const [badges, setBadges] = useState<PracticeAchievement[]>([]);
  const [leaderboardLoading, setLeaderboardLoading] = useState(() => !cachedMotivation);
  const [overviewLoading, setOverviewLoading] = useState(() => !cachedMotivation);
  const [badgesLoading, setBadgesLoading] = useState(true);
  // 后端可能一次补发多枚历史达标勋章，使用队列逐个展示，避免弹窗互相覆盖。
  const [achievementNotices, setAchievementNotices] = useState<PracticeAchievement[]>([]);
  useEffect(() => {
    if (showPractice) return;
    if (!practiceLearners.length) setLeaderboardLoading(true);
    void practiceApi.leaderboard(range)
      .then(({ items }) => {
        const mapped = items.map((item) => ({ name: item.name, avatar: item.name.slice(0, 1), tone: String(item.userId) === getCurrentUserId() ? "me" : "blue", answers: item.answers, accuracy: item.accuracy, minutes: Math.round(item.studySeconds / 60), score: item.score, streak: 0, isMe: String(item.userId) === getCurrentUserId() }));
        setPracticeLearners(mapped);
        writeMotivationCache({ learners: mapped });
      })
      .catch(() => setPracticeLearners([]))
      .finally(() => setLeaderboardLoading(false));
  }, [range, showPractice]);
  useEffect(() => {
    if (showPractice) return;
    if (!cachedMotivation) setOverviewLoading(true);
    void practiceApi.overview("week")
      .then((stats) => { setWeeklyStats(stats); writeMotivationCache({ weeklyStats: stats }); })
      .catch(() => setWeeklyStats({ answerCount: 0, correctCount: 0, accuracy: 0 }))
      .finally(() => setOverviewLoading(false));
  }, [showPractice]);
  // 首屏走轻量接口；用户完成答题后才强制计算一次完整进度和新解锁勋章。
  const applyAchievements = (result: Awaited<ReturnType<typeof practiceApi.achievements>>) => {
    setBadges(result.items);
    setAchievementNotices((current) => {
      const merged = [...current];
      // 答题后可能连续刷新，用 ID 去重可以防止同一枚勋章进入队列多次。
      result.newlyUnlocked.forEach((item) => { if (!merged.some((existing) => existing.id === item.id)) merged.push(item); });
      return merged;
    });
  };
  const loadAchievementCatalog = () => void practiceApi.achievements()
    .then(applyAchievements)
    .catch(() => setBadges([]))
    .finally(() => setBadgesLoading(false));
  const refreshAchievements = () => void practiceApi.achievementProgress(true)
    .then(applyAchievements)
    .catch(() => undefined);
  useEffect(() => { if (!showPractice) loadAchievementCatalog(); }, [showPractice]);
  const currentLearner: Learner = { name: nickname || "我", avatar: "我", tone: "me", answers: 0, accuracy: 0, minutes: 0, score: 0, streak: 0, isMe: true };
  // 接口异常时只保留当前用户的空数据，绝不再回退到演示排行榜。
  const rankingSource = practiceLearners.some((item) => item.isMe) ? practiceLearners : [...practiceLearners, currentLearner];
  const sorted = useMemo(() => [...rankingSource].sort((a, b) => valueFor(b, ranking) - valueFor(a, ranking)), [ranking, rankingSource]);
  const me = sorted.find((item) => item.isMe)!;
  const myRank = sorted.findIndex((item) => item.isMe) + 1;
  const visibleBadges = badgeFilter === "earned" ? badges.filter((badge) => badge.earned) : badges;
  const earnedBadges = badges.filter((badge) => badge.earned);
  const activeTab = rankingTabs.find((tab) => tab.key === ranking)!;
  const challengePercent = Math.min(100, Math.round(weeklyStats.answerCount / 200 * 100));
  const level = Math.floor(me.score / 500) + 1;
  const nextLevelScore = level * 500;
  const levelProgress = Math.round(((me.score % 500) / 500) * 100);
  const podiumEntries = [
    { learner: sorted[1], rank: 2 },
    { learner: sorted[0], rank: 1 },
    { learner: sorted[2], rank: 3 },
  ].filter((entry): entry is { learner: Learner; rank: number } => Boolean(entry.learner));
  const achievementNotice = achievementNotices[0];
  const closeAchievementNotice = () => {
    if (!achievementNotice) return;
    // 先让界面立即关闭，再异步记录已通知状态，避免网络延迟影响交互。
    void practiceApi.acknowledgeAchievement(achievementNotice.id).catch(() => undefined);
    setAchievementNotices((items) => items.slice(1));
  };
  const achievementPopup = achievementNotice && <div className="achievement-unlock-backdrop"><section className="achievement-unlock-modal" role="dialog" aria-modal="true" aria-labelledby="achievement-unlock-title"><span className="achievement-unlock-rays" /><div className={`badge-medal ${achievementNotice.tone}`}><span>{achievementNotice.icon}</span><b><Icon name="check" size={11} /></b></div><span className="eyebrow">ACHIEVEMENT UNLOCKED</span><h2 id="achievement-unlock-title">解锁新勋章</h2><h3>{achievementNotice.title}</h3><p>{achievementNotice.detail}</p><button className="primary-button" onClick={closeAchievementNotice}>收下勋章</button></section></div>;

  if (showPractice) return <div className="motivation-practice-mode"><div className="motivation-practice-toolbar"><button className="outline-button" onClick={() => setShowPractice(false)}>← 返回荣誉排行</button></div><PracticeView bookId={bookId} bookTitle={bookTitle} onProgress={refreshAchievements} />{achievementPopup}</div>;
  // 勋章统计比排行榜更重：它在后台加载，不再阻塞用户先查看自己的答题和排行数据。
  if (leaderboardLoading || overviewLoading) return <div className="page-stack motivation-page motivation-loading-page"><div className="page-header motivation-header"><div><span className="eyebrow">LEARN · GROW · SHINE</span><h1>荣誉排行</h1><p>正在同步你的答题和学习数据…</p></div></div><section className="motivation-loading-card"><div className="loading-orbit">✦</div><strong>正在加载真实学习数据</strong><span>不会展示演示排行榜</span></section></div>;

  return (
    <div className="page-stack motivation-page">
      <div className="page-header motivation-header">
        <div><span className="eyebrow">LEARN · GROW · SHINE</span><h1>荣誉排行</h1><p>让每一次练习和专注，都成为看得见的成长。</p></div>
        <div className="motivation-streak"><span>🔥</span><div><strong>{me.streak} 天</strong><small>连续学习中</small></div></div>
      </div>

      <div className="motivation-practice-entry"><div><strong>无限答题挑战</strong><span>答题数和正确率会实时计入排行榜</span></div><button className="primary-button" onClick={() => setShowPractice(true)}>开始无限答题 <Icon name="arrow-right" size={15} /></button></div>

      <section className="motivation-hero">
        <div className="motivation-hero-copy">
          <button className="motivation-kicker score-rules-trigger" onClick={() => setShowScoreRules(true)}>加分细则 <Icon name="info" size={12} /></button>
          <h2>{nickname || "同学"}，本周已获得 <em>{me.score} XP</em></h2>
          <p>继续完成答题和学习任务，综合成长积分会实时更新。</p>
          <div className="motivation-level"><div><strong>Lv. {level}</strong><span>求知探索者</span></div><div className="motivation-level-track"><i style={{ width: `${levelProgress}%` }} /></div><b>{me.score.toLocaleString()} / {nextLevelScore.toLocaleString()} XP</b></div>
        </div>
        <div className="motivation-hero-stats">
          <div><span>当前排名</span><strong>#{myRank}</strong><small>较上周 ↑ 3</small></div>
          <div><span>本周答题</span><strong>{weeklyStats.answerCount}</strong><small>答对 {weeklyStats.correctCount} 题</small></div>
          <div><span>正确率</span><strong>{weeklyStats.accuracy}%</strong><small>基于本周有效作答</small></div>
        </div>
      </section>

      <section className="motivation-main-grid">
        <article className="card leaderboard-card">
          <div className="leaderboard-head">
            <div><h2>学习排行榜</h2><p>{activeTab.hint}</p></div>
            <div className="range-switch" aria-label="排行周期"><button className={range === "week" ? "active" : ""} onClick={() => setRange("week")}>本周</button><button className={range === "month" ? "active" : ""} onClick={() => setRange("month")}>本月</button></div>
          </div>
          <div className="ranking-tabs">{rankingTabs.map((tab) => <button key={tab.key} className={ranking === tab.key ? "active" : ""} onClick={() => setRanking(tab.key)}>{tab.label}</button>)}</div>
          <div className="podium" aria-label={`${range === "week" ? "本周" : "本月"}前三名`}>
            {podiumEntries.map(({ learner, rank }) => <div className={`podium-item rank-${rank}`} key={learner.name}><span className="podium-crown">{rank === 1 ? "♛" : `#${rank}`}</span><div className={`leader-avatar ${learner.tone}`}>{learner.avatar}</div><strong>{learner.name}</strong><small>{metricText(learner, ranking)}</small><i /></div>)}
          </div>
          <div className="ranking-list">{sorted.slice(3).map((learner, index) => <div className={`ranking-row ${learner.isMe ? "is-me" : ""}`} key={learner.name}><b className="rank-number">{index + 4}</b><div className={`leader-avatar small ${learner.tone}`}>{learner.avatar}</div><div className="leader-name"><strong>{learner.isMe ? nickname || "你" : learner.name}</strong><span>{learner.isMe ? "这是你 · 继续冲榜" : `连续学习 ${learner.streak} 天`}</span></div><strong className="leader-value">{metricText(learner, ranking)}</strong>{learner.isMe && <span className="me-tag">我</span>}</div>)}</div>
        </article>

        <aside className="motivation-side">
          <article className="card weekly-challenge">
            <div className="card-heading"><span>本周挑战</span><span className="challenge-time">还剩 2 天</span></div>
            <div className="challenge-icon"><Icon name="trophy" size={25} /></div>
            <h3>冲刺 200 题</h3><p>完成挑战可获得限定勋章和 300 XP</p>
            <div className="challenge-progress"><span><b>{weeklyStats.answerCount}</b> / 200 题</span><strong>{challengePercent}%</strong><div><i style={{ width: `${challengePercent}%` }} /></div></div>
            <button className="primary-button full" onClick={() => setShowPractice(true)}>继续答题 <Icon name="arrow-right" size={15} /></button>
          </article>
          <article className="card honor-summary">
            <div className="card-heading"><span>我的荣誉</span><button onClick={() => setBadgeFilter(badgeFilter === "all" ? "earned" : "all")}>{badgeFilter === "all" ? "仅看已获得" : "查看全部"}</button></div>
            <div className="honor-number"><strong>{badgesLoading ? "—" : earnedBadges.length}</strong><span>已获得勋章</span><i>{badgesLoading ? "正在读取" : `共 ${badges.length} 枚`}</i></div>
            <div className="recent-honors">{badgesLoading ? <small>正在读取已获得勋章…</small> : <>{earnedBadges.slice(0, 3).map((badge) => <span key={badge.id} title={badge.title}>{badge.icon}</span>)}{earnedBadges.length > 3 && <span className="more-honors">+{earnedBadges.length - 3}</span>}{badges.length > 0 && earnedBadges.length === 0 && <small>继续学习，解锁第一枚勋章</small>}</>}</div>
          </article>
        </aside>
      </section>

      <section className="card badge-wall">
        <div className="badge-wall-head"><div><h2>荣誉勋章墙</h2><p>完成学习里程碑，收集属于你的成长印记。</p></div><span>{badgesLoading ? "正在读取" : `已解锁 ${earnedBadges.length} / ${badges.length}`}</span></div>
        {!badgesLoading && <div className="badge-grid">{visibleBadges.map((badge) => <article className={`badge-item ${badge.earned ? "earned" : ""}`} key={badge.id}><div className={`badge-medal ${badge.tone}`}><span>{badge.icon}</span>{badge.earned && <b><Icon name="check" size={11} /></b>}</div><strong>{badge.title}</strong><p>{badge.detail}</p><div className="badge-progress"><i style={{ width: `${badge.progress}%` }} /></div><small>{badge.earned ? "已获得" : badge.statusText}</small></article>)}</div>}
        {badgesLoading && <div className="badge-empty">正在读取你已获得的勋章…</div>}
        {!badgesLoading && badges.length === 0 && <div className="badge-empty">勋章进度暂时无法加载，请稍后重试。</div>}
      </section>
      {showScoreRules && <div className="score-rules-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowScoreRules(false); }}><section className="score-rules-modal" role="dialog" aria-modal="true" aria-labelledby="score-rules-title"><header><div><span className="eyebrow">GROWTH POINTS</span><h2 id="score-rules-title">综合成长加分细则</h2><p>答题质量、任务完成与学习投入共同计分</p></div><button className="icon-button" onClick={() => setShowScoreRules(false)} aria-label="关闭加分细则"><Icon name="close" size={18} /></button></header><div className="score-rules-modal-grid"><div><b>+2 XP</b><span>完成一道有效答题</span></div><div><b>+8 XP</b><span>回答正确额外奖励</span></div><div><b>+20 XP</b><span>完成一个学习任务</span></div><div><b>+5 XP</b><span>每满10分钟有效学习</span></div><div><b>+10 XP</b><span>每连续答对5题</span></div></div><footer><Icon name="info" size={15} /><span>单个任务学习时长最多计4小时；重复提交不重复计分。</span></footer></section></div>}
      {achievementPopup}
    </div>
  );
}
