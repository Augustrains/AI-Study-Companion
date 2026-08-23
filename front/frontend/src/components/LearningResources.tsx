import { useEffect, useState } from "react";
import { Icon, type IconName } from "./Icon";
import { api, type KnowledgePointResources, type LearningResource } from "../services/api";

/**
 * 知识点延伸学习资源。
 * 资源来自后端 GET /learning-resources（数据文件 data/learning_resources/resources.json），
 * 每条链接都是核实过可访问的；没有收录的知识点显示空态，不编造链接。
 */

const PLATFORM_LABELS: Record<string, string> = {
  bilibili: "B 站",
  youtube: "YouTube",
  coursera: "Coursera",
  edx: "edX",
  other: "在线教程",
};

const KIND_ICONS: Record<string, IconName> = {
  video: "spark",
  course: "book-open",
  article: "file",
};

export function ResourceLinkList({ resources }: { resources: LearningResource[] }) {
  if (resources.length === 0) {
    return (
      <div className="resource-empty">
        <Icon name="info" size={15} />
        <span>这个知识点还没有收录延伸资源。</span>
      </div>
    );
  }
  return (
    <div className="resource-list">
      {resources.map((resource) => (
        <a
          className="resource-item"
          key={`${resource.url}-${resource.title}`}
          href={resource.url}
          target="_blank"
          rel="noreferrer noopener"
        >
          <span className={`resource-icon platform-${resource.platform}`}>
            <Icon name={KIND_ICONS[resource.kind] ?? "spark"} size={15} />
          </span>
          <span className="resource-body">
            <strong>{resource.title}</strong>
            <small>{resource.note}</small>
            <span className="resource-tags">
              <i>{PLATFORM_LABELS[resource.platform] ?? resource.platform}</i>
              <i>{resource.language === "zh" ? "中文" : "英文"}</i>
            </span>
          </span>
          <Icon name="arrow-up-right" size={15} />
        </a>
      ))}
    </div>
  );
}

/** 内嵌在知识点详情 / 任务详情 / 问答拒答处的小块资源推荐 */
export function InlineResources({ knowledgePointIds, title = "延伸学习" }: { knowledgePointIds: string[]; title?: string }) {
  const [resources, setResources] = useState<LearningResource[] | null>(null);

  useEffect(() => {
    let active = true;
    if (knowledgePointIds.length === 0) {
      setResources([]);
      return;
    }
    void api.getLearningResources(knowledgePointIds)
      .then((result) => {
        if (!active) return;
        // 多个知识点的资源合并去重
        const merged = new Map<string, LearningResource>();
        for (const item of result.items) {
          for (const resource of item.resources) merged.set(resource.url, resource);
        }
        setResources([...merged.values()]);
      })
      .catch(() => active && setResources([]));
    return () => { active = false; };
  }, [knowledgePointIds.join(",")]);

  if (resources === null) return <div className="resource-loading">正在查找相关资源…</div>;
  if (resources.length === 0) return null;

  return (
    <div className="inline-resources">
      <div className="inline-resources-head"><Icon name="spark" size={15} />{title}</div>
      <ResourceLinkList resources={resources} />
    </div>
  );
}

/** 侧边栏「学习资源」独立页面 */
export function LearningResourcesView({ knowledgePointNames }: { knowledgePointNames: Record<string, string> }) {
  const [items, setItems] = useState<KnowledgePointResources[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    void api.getLearningResources()
      .then((result) => {
        if (!active) return;
        const withResources = result.items.filter((item) => item.resources.length > 0);
        setItems(withResources);
        setExpanded(withResources[0]?.knowledgePointId ?? null);
      })
      .catch(() => active && setItems([]))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const label = (id: string) => knowledgePointNames[id] || id;
  const filtered = keyword.trim()
    ? items.filter((item) =>
        label(item.knowledgePointId).includes(keyword.trim()) ||
        item.resources.some((resource) => resource.title.toLowerCase().includes(keyword.trim().toLowerCase())))
    : items;
  const total = items.reduce((sum, item) => sum + item.resources.length, 0);

  return (
    <div className="page-stack narrow-page">
      <div className="page-header">
        <div>
          <span className="eyebrow">Resources</span>
          <h1>学习资源</h1>
          <p>按知识点整理的视频课程、公开课与在线教材，全部链接均已核实可访问。</p>
        </div>
      </div>

      {loading ? (
        <div className="card" style={{ padding: 28 }}><div className="onboard-loading">正在加载学习资源…</div></div>
      ) : items.length === 0 ? (
        <div className="card" style={{ padding: 28 }}>
          <div className="empty-state"><Icon name="file" size={21} /><strong>还没有收录学习资源</strong><span>后端资源文件为空。</span></div>
        </div>
      ) : (
        <>
          <div className="card resource-toolbar">
            <div className="resource-search">
              <Icon name="filter" size={15} />
              <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索知识点或资源名称" />
            </div>
            <span className="resource-count">{items.length} 个知识点 · {total} 条资源</span>
          </div>

          <div className="resource-groups">
            {filtered.map((item) => {
              const open = expanded === item.knowledgePointId;
              return (
                <div className={`card resource-group ${open ? "open" : ""}`} key={item.knowledgePointId}>
                  <button
                    type="button"
                    className="resource-group-head"
                    onClick={() => setExpanded(open ? null : item.knowledgePointId)}
                  >
                    <div>
                      <strong>{label(item.knowledgePointId)}</strong>
                      <small>{item.knowledgePointId} · {item.resources.length} 条资源</small>
                    </div>
                    <Icon name={open ? "chevron-down" : "chevron-right"} size={17} />
                  </button>
                  {open && <ResourceLinkList resources={item.resources} />}
                </div>
              );
            })}
            {filtered.length === 0 && (
              <div className="card" style={{ padding: 24 }}>
                <div className="empty-state"><Icon name="file" size={21} /><strong>没有匹配的资源</strong><span>换个关键词试试。</span></div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
