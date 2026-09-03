import { useEffect, useId, useMemo, useReducer, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Icon } from "./Icon";
import { communityComments, communityGroups, communityPeople, communityPosts, type CommunityPerson } from "../data/communityMockData";
import { communityCategories, communityReducer, loadCommunityState, saveCommunityState, type CommunityCategory, type CommunityPost } from "../data/communityState";
import "./community.css";

type Filter = "全部" | CommunityCategory | "我的收藏";
type DialogState = "publish" | "reset" | CommunityPerson | null;
const filters: Filter[] = ["全部", ...communityCategories, "我的收藏"];
const avatarColor = (id: string) => communityPeople.find((person) => person.id === id)?.color ?? "blue";
const displayTime = (value: string) => value.startsWith("示例") ? value.replace("示例 · ", "") : new Date(value).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
function browserStorage() {
  try { return window.localStorage; } catch { return undefined; }
}

function Avatar({ name, color = "blue", large = false }: { name: string; color?: string; large?: boolean }) {
  return <span aria-hidden="true" className={`community-avatar community-tone-${color}${large ? " community-avatar-large" : ""}`}>{name.slice(0, 1)}</span>;
}

function CommunityDialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    return () => { dialog?.close(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} className="community-dialog" aria-labelledby={titleId} onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="community-dialog-inner">
      <header><h2 id={titleId}>{title}</h2><button type="button" className="community-icon-button" aria-label="关闭弹窗" onClick={onClose}><Icon name="close" /></button></header>
      {children}
    </div>
  </dialog>;
}

function PublishForm({ course, onPublish }: { course: string; onPublish: (category: CommunityCategory, course: string, title: string, body: string) => void }) {
  const [category, setCategory] = useState<CommunityCategory>("学习分享");
  const [postCourse, setPostCourse] = useState(course || "人工智能基础");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const courses = [...new Set([course, "机器学习", "深度学习", "Python实操", "人工智能基础"].filter(Boolean))];
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (title.trim() && body.trim()) onPublish(category, postCourse, title.trim(), body.trim());
  };
  return <form className="community-form" onSubmit={submit}>
    <p className="community-form-intro">一个新理解、一处小困惑，都值得被分享。</p>
    <div className="community-form-row">
      <label>动态分类<select value={category} onChange={(event) => setCategory(event.target.value as CommunityCategory)}>{communityCategories.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label>课程标签<select value={postCourse} onChange={(event) => setPostCourse(event.target.value)}>{courses.map((item) => <option key={item}>{item}</option>)}</select></label>
    </div>
    <label>标题<input autoFocus required maxLength={96} placeholder="给你的分享起个标题" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
    <label>分享内容<textarea required maxLength={1200} rows={6} placeholder="说说你的学习发现，或介绍你想找的学习搭子…" value={body} onChange={(event) => setBody(event.target.value)} /></label>
    <div className="community-form-hint"><span>仅保存到此浏览器，不会公开发布。</span><span>{body.length} / 1200</span></div>
    <button type="submit" className="primary-button" disabled={!title.trim() || !body.trim()}><Icon name="send" size={16} />发布到示例社区</button>
  </form>;
}

export function CommunityView({ userId, nickname, course }: { userId: string; nickname: string; course: string }) {
  const [state, dispatch] = useReducer(communityReducer, userId, (id) => loadCommunityState(id, browserStorage()));
  const [filter, setFilter] = useState<Filter>("全部");
  const [query, setQuery] = useState("");
  const [dialog, setDialog] = useState<DialogState>(null);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [persistent, setPersistent] = useState(true);
  useEffect(() => { setPersistent(saveCommunityState(userId, state, browserStorage())); }, [state, userId]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const posts = useMemo(() => [...state.posts, ...communityPosts].filter((post) => {
    const matchesFilter = filter === "全部" || (filter === "我的收藏" ? state.savedIds.includes(post.id) : post.category === filter);
    const text = [post.title, post.body, post.authorName, post.course].join(" ").toLocaleLowerCase();
    return matchesFilter && text.includes(query.trim().toLocaleLowerCase());
  }), [state.posts, state.savedIds, filter, query]);
  const comments = useMemo(() => [...communityComments, ...state.comments], [state.comments]);
  const suggestions = [...communityPeople].sort((a, b) => Number(b.course === course) - Number(a.course === course)).slice(0, 3);
  const toggleFollow = (person: CommunityPerson) => {
    dispatch({ type: "toggle", field: "followedIds", id: person.id });
    setNotice(state.followedIds.includes(person.id) ? `已取消关注${person.name}` : `已关注${person.name}，一起保持学习的节奏`);
  };
  const publish = (category: CommunityCategory, postCourse: string, title: string, body: string) => {
    dispatch({ type: "post", post: { id: `local-${crypto.randomUUID()}`, authorId: userId, authorName: nickname.slice(0, 100) || "学习者", category, course: postCourse.slice(0, 80), title, body, createdAt: new Date().toISOString(), likes: 0 } });
    setFilter("全部"); setQuery(""); setDialog(null); setNotice("动态已添加到示例社区，仅此浏览器可见");
  };
  const comment = (event: FormEvent, post: CommunityPost) => {
    event.preventDefault();
    const body = drafts[post.id]?.trim();
    if (!body) return;
    dispatch({ type: "comment", comment: { id: `comment-${crypto.randomUUID()}`, postId: post.id, authorName: nickname.slice(0, 100) || "学习者", body } });
    setDrafts((current) => ({ ...current, [post.id]: "" }));
    setNotice("评论已添加，仅此浏览器可见");
  };
  return <section className="community-page" aria-labelledby="community-heading">
    <div className="page-header community-page-header"><div><span className="eyebrow">LEARN TOGETHER</span><h1 id="community-heading">学习社区</h1><p>分享你的发现，遇见同路的学习伙伴。</p></div><span className="community-demo-tag"><span />示例社区</span></div>

    <div className="community-hero">
      <div className="community-hero-copy"><span className="community-kicker"><Icon name="spark" size={15} />让学习发生连接</span><h2>一个人的探索，<br />一群人的灵感。</h2><p>从一次提问到一份笔记，让每一个小进步，都有人回应。</p><button className="community-hero-button" onClick={() => setDialog("publish")}><Icon name="plus" size={17} />分享我的学习<Icon name="arrow-right" size={17} /></button></div>
      <div className="community-orbit" aria-hidden="true"><div className="community-orbit-ring" /><div className="community-orbit-ring inner" /><span className="community-orbit-center"><Icon name="users" size={40} /></span><span className="community-orbit-person orbit-one"><Avatar name="小沐" color="blue" large /></span><span className="community-orbit-person orbit-two"><Avatar name="林同学" color="mint" large /></span><span className="community-orbit-person orbit-three"><Avatar name="阿予" color="violet" large /></span><span className="community-orbit-note"><Icon name="check-circle" size={16} />今天，又理解了一点</span><span className="community-orbit-spark">✦</span></div>
    </div>

    <div className="community-layout">
      <div className="community-feed">
        <div className="community-composer"><Avatar name={nickname || "我"} /><button onClick={() => setDialog("publish")}>今天有什么新的学习发现？</button><button className="community-compose-icon" aria-label="发布动态" onClick={() => setDialog("publish")}><Icon name="plus" /></button></div>
        <div className="community-feed-tools"><div className="community-filters" role="group" aria-label="动态分类筛选">{filters.map((item) => <button key={item} aria-pressed={filter === item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item}</button>)}</div><label className="community-search"><Icon name="search" size={16} /><input aria-label="搜索社区动态" placeholder="搜索话题、课程或伙伴" value={query} maxLength={100} onChange={(event) => setQuery(event.target.value)} /></label></div>
        <p className="community-results" role="status">{query.trim() ? `搜索结果 · ${posts.length} 条动态` : filter === "我的收藏" ? `我的收藏 · ${posts.length} 条动态` : "每一种理解，都值得交流"}</p>
        <div className="community-posts">
          {posts.map((post) => {
            const author = communityPeople.find((person) => person.id === post.authorId);
            const postComments = comments.filter((item) => item.postId === post.id);
            const isExpanded = expanded.includes(post.id);
            const liked = state.likedIds.includes(post.id);
            const saved = state.savedIds.includes(post.id);
            return <article key={post.id} className="community-post" aria-labelledby={`title-${post.id}`}>
              <header className="community-post-header"><button className="community-author" disabled={!author} aria-label={`查看${post.authorName}的资料`} onClick={() => author && setDialog(author)}><Avatar name={post.authorName} color={avatarColor(post.authorId)} /><span><strong>{post.authorName}</strong><small>{author?.role ?? "我的学习动态"} · {displayTime(post.createdAt)}</small></span></button><span className={`community-category ${post.category === "寻找搭子" ? "mint" : post.category === "问题讨论" ? "violet" : ""}`}>{post.category}</span></header>
              <h3 id={`title-${post.id}`}>{post.title}</h3><p className="community-post-body">{post.body}</p>
              {post.id === "seed-1" && <div className="community-note"><span className="community-note-label"><Icon name="book-open" size={16} />我的理解笔记</span><div><span>训练误差</span><Icon name="plus" size={13} /><span>验证误差</span><Icon name="arrow-right" size={16} /><strong>一起看，才完整</strong></div></div>}
              <div className="community-post-tags"><button onClick={() => { setQuery(post.course); setFilter("全部"); }}># {post.course}</button>{post.category === "寻找搭子" && <span><Icon name="clock" size={13} />{author?.time ?? "一起商量学习时间"}</span>}</div>
              <footer className="community-post-actions"><button aria-label={`${liked ? "取消点赞" : "点赞"}：${post.title}`} aria-pressed={liked} className={liked ? "liked" : ""} onClick={() => dispatch({ type: "toggle", field: "likedIds", id: post.id })}><Icon name="heart" size={17} /><span>{post.likes + (liked ? 1 : 0)}</span></button><button aria-label={`评论：${post.title}`} aria-expanded={isExpanded} aria-controls={`comments-${post.id}`} onClick={() => setExpanded((current) => isExpanded ? current.filter((id) => id !== post.id) : [...current, post.id])}><Icon name="chat" size={17} /><span>{postComments.length ? postComments.length : "评论"}</span></button><button className={`community-save ${saved ? "saved" : ""}`} aria-label={`${saved ? "取消收藏" : "收藏"}：${post.title}`} aria-pressed={saved} onClick={() => dispatch({ type: "toggle", field: "savedIds", id: post.id })}><Icon name="bookmark" size={17} /><span>{saved ? "已收藏" : "收藏"}</span></button></footer>
              {isExpanded && <section id={`comments-${post.id}`} className="community-comments" aria-label={`${post.title}的评论`}>
                {postComments.length === 0 ? <p className="community-muted">成为第一个分享想法的人。</p> : postComments.map((item) => <div key={item.id} className="community-comment"><Avatar name={item.authorName} color="mint" /><p><strong>{item.authorName}</strong><span>{item.body}</span></p></div>)}
                <form onSubmit={(event) => comment(event, post)}><input aria-label={`回复：${post.title}`} placeholder="分享你的思路，友善地交流…" maxLength={300} value={drafts[post.id] ?? ""} onChange={(event) => setDrafts((current) => ({ ...current, [post.id]: event.target.value }))} /><button aria-label={`发送评论：${post.title}`} disabled={!drafts[post.id]?.trim()}><Icon name="send" size={17} /></button></form>
              </section>}
            </article>;
          })}
          {posts.length === 0 && <div className="community-empty"><Icon name={filter === "我的收藏" ? "bookmark" : "search"} size={30} /><h3>{filter === "我的收藏" ? "把想再看的灵感留在这里" : "还没有找到相关动态"}</h3><p>{filter === "我的收藏" ? "点击动态下方的收藏，就能在这里再次找到它。" : "试试“机器学习”“学习率”，或换一个分类。"}</p><button className="secondary-button" onClick={() => { setFilter("全部"); setQuery(""); }}>看看全部动态</button></div>}
        </div>
        <p className="community-feed-end">学习不必独行，下一份灵感也许来自你。</p>
      </div>

      <aside className="community-rail" aria-label="学习伙伴与小组">
        <section className="community-side-card"><div className="community-side-heading"><h2>遇见学习搭子</h2><Icon name="users" size={19} /></div><p className="community-side-description">从相近的学习兴趣开始</p>{suggestions.map((person) => <div key={person.id} className="community-person"><button className="community-person-profile" aria-label={`查看${person.name}的资料`} onClick={() => setDialog(person)}><Avatar name={person.name} color={person.color} /><span><strong>{person.name}</strong><small>{person.goal}</small></span></button><div className="community-person-tags">{person.tags.map((tag) => <span key={tag}>{tag}</span>)}</div><div className="community-person-bottom"><span>{person.course}</span><button aria-label={`${state.followedIds.includes(person.id) ? "取消关注" : "关注"}${person.name}`} aria-pressed={state.followedIds.includes(person.id)} className={state.followedIds.includes(person.id) ? "following" : ""} onClick={() => toggleFollow(person)}><Icon name={state.followedIds.includes(person.id) ? "check" : "plus"} size={13} />{state.followedIds.includes(person.id) ? "已关注" : "关注"}</button></div></div>)}</section>
        <section className="community-side-card"><div className="community-side-heading"><h2>找到你的学习圈</h2><Icon name="spark" size={19} /></div><p className="community-side-description">同一个主题，不一样的视角</p>{communityGroups.map((group) => <div className="community-group" key={group.id}><span className={`community-group-icon community-tone-${group.color}`}><Icon name={group.icon} size={18} /></span><div><strong>{group.name}</strong><small>{group.detail}</small><button aria-label={`${state.joinedIds.includes(group.id) ? "退出" : "加入"}${group.name}`} aria-pressed={state.joinedIds.includes(group.id)} onClick={() => { dispatch({ type: "toggle", field: "joinedIds", id: group.id }); setNotice(state.joinedIds.includes(group.id) ? `已退出${group.name}` : `已加入${group.name}（本地展示）`); }}>{state.joinedIds.includes(group.id) ? "已加入 · 点击退出" : "加入小组 →"}</button></div></div>)}</section>
        <section className="community-guideline"><Icon name="shield" size={20} /><div><h2>让交流有温度</h2><p>分享思路，尊重不同理解。<br />多一点启发，少一点直接代答。</p></div></section>
        <div className="community-demo-info"><p>示例人物与动态用于交互展示。发帖、评论和关注仅保存在此浏览器，不会发送给其他用户。</p>{!persistent && <p role="alert">浏览器存储不可用，操作暂存在当前会话，刷新后可能丢失。</p>}<button onClick={() => setDialog("reset")}>恢复初始示例</button></div>
      </aside>
    </div>
    <div className={`community-notice ${notice ? "visible" : ""}`} role="status" aria-live="polite">{notice && <><Icon name="check-circle" size={18} />{notice}</>}</div>

    {dialog === "publish" && <CommunityDialog title="分享你的学习" onClose={() => setDialog(null)}><PublishForm course={course} onPublish={publish} /></CommunityDialog>}
    {dialog === "reset" && <CommunityDialog title="恢复初始示例？" onClose={() => setDialog(null)}><p className="community-reset-copy">这将清除当前账号在此浏览器的社区发帖、评论、点赞、收藏、关注和加入记录。学习计划、画像及其他账号的数据不会改变。</p><div className="community-dialog-actions"><button className="secondary-button" onClick={() => setDialog(null)}>取消</button><button className="primary-button" onClick={() => { dispatch({ type: "reset" }); setExpanded([]); setDrafts({}); setQuery(""); setFilter("全部"); setDialog(null); setNotice("已恢复初始示例"); }}>确认恢复</button></div></CommunityDialog>}
    {dialog && typeof dialog === "object" && <CommunityDialog title="学习伙伴" onClose={() => setDialog(null)}><div className="community-profile-detail"><Avatar name={dialog.name} color={dialog.color} large /><h3>{dialog.name}</h3><p>{dialog.role}</p><span className="community-category">{dialog.course}</span><p className="community-profile-bio">{dialog.bio}</p><dl><div><dt>学习目标</dt><dd>{dialog.goal}</dd></div><div><dt>学习时间</dt><dd>{dialog.time}</dd></div><div><dt>交流偏好</dt><dd>{dialog.tags.join(" · ")}</dd></div></dl><button className="primary-button" aria-pressed={state.followedIds.includes(dialog.id)} onClick={() => toggleFollow(dialog)}><Icon name={state.followedIds.includes(dialog.id) ? "check" : "plus"} size={16} />{state.followedIds.includes(dialog.id) ? "已关注 · 取消关注" : "关注这位伙伴"}</button><small>示例资料，关注不会向真实用户发送通知。</small></div></CommunityDialog>}
  </section>;
}
