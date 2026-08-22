import { useState } from "react";
import { Icon, type IconName } from "./Icon";
import type { NavKey } from "../data/mockData";

/**
 * 帮助中心。
 * 原来只是一个两条说明的弹窗，信息量太少。改成一页「怎么用」：
 *   1. 顶部把学习闭环六步画出来，让用户先建立整体心智模型；
 *   2. 按页面分块讲用法，点开即展开，并可直接跳到该页面；
 *   3. 底部收常见疑问（为什么推荐这个任务、AI 判断与我的校准有何区别等）。
 */

type PageGuide = {
  nav: NavKey;
  icon: IconName;
  title: string;
  summary: string;
  steps: string[];
  tip?: string;
};

const LOOP_STEPS = [
  { label: "选书与目标", desc: "确定学什么、学到什么程度" },
  { label: "能力诊断", desc: "做题收集你的真实水平" },
  { label: "AI 判断 + 你的校准", desc: "两份判断分开保存" },
  { label: "生成学习计划", desc: "按薄弱项排出任务顺序" },
  { label: "完成任务", desc: "记录用时，写入学习事件" },
  { label: "到期复测", desc: "按记忆规律安排复习" },
];

const PAGE_GUIDES: PageGuide[] = [
  {
    nav: "goals",
    icon: "target",
    title: "选书与目标",
    summary: "所有功能的起点，决定后面诊断什么、推荐什么。",
    steps: [
      "选一本书（暂时开放《机器学习》《深度学习》，灰色的是还没上线的）。",
      "选目标水平——它决定任务难度，比如「独立完成基础练习」和「应对面试」排出的计划不一样。",
      "填每周能投入的小时数，右侧输入框不设上限。",
      "保存后系统会引导你做第一次能力诊断。",
    ],
    tip: "之后想换书或改目标，随时回到这一页重新保存即可。",
  },
  {
    nav: "diagnostic",
    icon: "target",
    title: "能力诊断",
    summary: "系统判断你会什么、不会什么的唯一依据。",
    steps: [
      "逐题作答，答案会一题一保存，中途关掉也不会丢。",
      "不确定的题可以「跳过」，跳过不算错，只是不产生证据。",
      "答完看到 AI 评估结果和判断依据。",
      "在右侧做「用户校准」：如果你觉得 AI 判高了或判低了，选一下并写原因。",
    ],
    tip: "复测时系统会优先出你没做过的题，题库用完了才会重复。",
  },
  {
    nav: "today",
    icon: "home",
    title: "今日学习",
    summary: "每天打开先看这里，它回答「我现在该做什么」。",
    steps: [
      "「今日推荐任务」是系统认为最该补的一项，点开能看到推荐理由。",
      "「今日任务队列」按顺序列出今天的安排，点任意一条看详情。",
      "完成任务时会问你实际花了多久——这个数字会用来校准之后的排课。",
      "「能力图谱」显示各知识点的掌握情况：绿色掌握良好、蓝色正在学、橙色薄弱、灰色未评估。",
    ],
    tip: "本周进度里的时长和正确率都来自真实记录，没有数据时会显示空态而不是假数字。",
  },
  {
    nav: "plan",
    icon: "calendar",
    title: "学习计划",
    summary: "看完整的任务排列，以及每一项为什么排在这里。",
    steps: [
      "「计划总览」按顺序列出全部任务、状态、预计用时和推荐理由。",
      "「知识点列表」换个角度按知识点看。",
      "右上角「调整目标」可以改目标水平，改完下次生成计划时生效。",
    ],
  },
  {
    nav: "records",
    icon: "chart",
    title: "学习记录",
    summary: "所有学习行为的流水，也是复测的入口。",
    steps: [
      "按类型筛选：学习画像、能力诊断、学习任务、资料问答。",
      "点任意一条看详情。",
      "需要复习时从这里进入复测。",
    ],
  },
  {
    nav: "qa",
    icon: "chat",
    title: "资料问答",
    summary: "围绕教材提问，每个回答都带出处。",
    steps: [
      "提问范围限定在当前书籍，回答会附上章节引用，可点开看原文。",
      "如果教材里找不到依据，系统会明确说「没找到」，而不是编一个答案。",
      "这时可以点「用通用模型回答」，但那类回答没有教材出处，会单独标注，也不计入学习记录。",
      "有用的回答可以「加入学习计划」，变成一个正式任务。",
    ],
    tip: "资料问答不会改变你的掌握度——掌握度只由诊断和练习产生。",
  },
  {
    nav: "resources",
    icon: "spark",
    title: "学习资源",
    summary: "按知识点整理的视频课程与公开课，教材之外的补充。",
    steps: [
      "按知识点折叠浏览，也可以搜索。",
      "在能力图谱节点、任务详情里也会出现对应知识点的资源。",
      "点击直接跳转到 B 站 / YouTube / Coursera 等平台。",
    ],
    tip: "所有链接都核实过可访问，没有收录资源的知识点会如实显示空态。",
  },
  {
    nav: "profile",
    icon: "user",
    title: "学习画像",
    summary: "补充你的背景和偏好，让推荐更贴合你。",
    steps: [
      "填写学习背景、自评水平、已掌握的知识点。",
      "写下当前困惑和额外要求。",
      "设置偏好：活动类型、内容风格、难度、单次时长、学习频率。",
    ],
  },
];

const FAQ = [
  {
    q: "为什么给我推荐这个任务？",
    a: "推荐依据来自最近一次能力诊断：系统找出正确率最低、且与你目标最相关的知识点优先补强。每个推荐任务下面都能看到具体理由（第几次诊断、几题答对几题）。",
  },
  {
    q: "AI 判断和我的校准有什么区别？",
    a: "AI 判断来自你的答题结果，用户校准是你的自我评估。两份分开保存、互不覆盖——生成计划时以你的校准为准，但原始 AI 判断始终可追溯。",
  },
  {
    q: "复习时间是怎么定的？",
    a: "按记忆规律安排：第一次验证通过后间隔较短，连续通过后间隔逐步拉长（1、2、4、7、15、30、60 天）。答错会缩短间隔，重新从短周期开始。",
  },
  {
    q: "为什么资料问答有时不回答？",
    a: "这是刻意设计的。资料问答的价值在于「答案有出处」，教材里找不到依据时宁可明说，也不编一个看起来合理的答案。需要的话可以显式切换到通用模型，但那类回答会明确标注为未经教材验证。",
  },
  {
    q: "完成任务时为什么要填实际用时？",
    a: "计划里的分钟数只是估计。你填的真实用时会和计划值一起记录下来，用于校准之后的排课——比如你总是比计划多花一倍时间，系统就该少排一点。",
  },
];

export function HelpCenterView({ onNavigate }: { onNavigate: (nav: NavKey) => void }) {
  const [openPage, setOpenPage] = useState<string | null>(PAGE_GUIDES[0].title);
  const [openFaq, setOpenFaq] = useState<string | null>(null);

  return (
    <div className="page-stack narrow-page">
      <div className="page-header">
        <div>
          <span className="eyebrow">Help</span>
          <h1>怎么用</h1>
          <p>先看一遍学习闭环，再按需要展开每个页面的用法。</p>
        </div>
      </div>

      <div className="card help-loop">
        <div className="card-heading"><span>学习闭环</span><small>系统按这个顺序运转，每一步的结果都会影响下一步</small></div>
        <div className="loop-steps">
          {LOOP_STEPS.map((step, index) => (
            <div className="loop-step" key={step.label}>
              <span className="loop-index">{index + 1}</span>
              <strong>{step.label}</strong>
              <small>{step.desc}</small>
              {index < LOOP_STEPS.length - 1 && <span className="loop-arrow"><Icon name="chevron-right" size={14} /></span>}
            </div>
          ))}
        </div>
      </div>

      <div className="help-section-title">按页面看用法</div>
      <div className="help-groups">
        {PAGE_GUIDES.map((guide) => {
          const open = openPage === guide.title;
          return (
            <div className={`card help-group ${open ? "open" : ""}`} key={guide.title}>
              <button type="button" className="help-group-head" onClick={() => setOpenPage(open ? null : guide.title)}>
                <span className="help-group-icon"><Icon name={guide.icon} size={17} /></span>
                <span className="help-group-title">
                  <strong>{guide.title}</strong>
                  <small>{guide.summary}</small>
                </span>
                <Icon name={open ? "chevron-down" : "chevron-right"} size={17} />
              </button>
              {open && (
                <div className="help-group-body">
                  <ol className="help-steps">
                    {guide.steps.map((step) => <li key={step}>{step}</li>)}
                  </ol>
                  {guide.tip && <div className="help-tip"><Icon name="info" size={14} /><span>{guide.tip}</span></div>}
                  <button className="outline-button" type="button" onClick={() => onNavigate(guide.nav)}>
                    去{guide.title} <Icon name="arrow-right" size={15} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="help-section-title">常见疑问</div>
      <div className="help-groups">
        {FAQ.map((item) => {
          const open = openFaq === item.q;
          return (
            <div className={`card help-group ${open ? "open" : ""}`} key={item.q}>
              <button type="button" className="help-group-head" onClick={() => setOpenFaq(open ? null : item.q)}>
                <span className="help-group-icon faq"><Icon name="help" size={16} /></span>
                <span className="help-group-title"><strong>{item.q}</strong></span>
                <Icon name={open ? "chevron-down" : "chevron-right"} size={17} />
              </button>
              {open && <div className="help-group-body"><p className="help-answer">{item.a}</p></div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
