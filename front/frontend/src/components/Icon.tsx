export type IconName = "home" | "target" | "calendar" | "chart" | "chat" | "user" | "settings" | "help" | "book-open" | "book" | "chevron-down" | "chevron-right" | "arrow-right" | "arrow-up-right" | "check" | "check-circle" | "clock" | "spark" | "file" | "send" | "info" | "filter" | "plus" | "more" | "close" | "alert" | "shield" | "bell" | "download" | "trash" | "log-out" | "lock" | "users" | "heart" | "bookmark" | "search";

const paths: Record<IconName, string> = {
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm8-7a4 4 0 0 1 0 8m5 9v-2a4 4 0 0 0-3-3.87",
  heart: "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z",
  bookmark: "M6 3h12v18l-6-4-6 4V3Z",
  search: "M21 21l-5-5m2-6a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  home: "M3 10.5 12 3l9 7.5M5.5 9v10h5v-6h3v6h5V9M8 20h8",
  target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-4a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-4a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z",
  calendar: "M5 4h14a2 2 0 0 1 2 2v13H3V6a2 2 0 0 1 2-2Zm-2 5h18M8 2v4m8-4v4",
  chart: "M4 19V5m0 14h17M8 16v-4m4 4V8m4 8V5m4 11v-7",
  chat: "M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v7a2.5 2.5 0 0 1-2.5 2.5H11l-5.5 4v-4.3A2.5 2.5 0 0 1 4 12.5v-7Z",
  user: "M20 21a8 8 0 0 0-16 0m12-13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  settings: "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-1.41 1.41-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V20h-2v-.09a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-1.41-1.41.06-.06A1.7 1.7 0 0 0 9.4 15a1.7 1.7 0 0 0-1.56-1.03H7v-2h.84A1.7 1.7 0 0 0 9.4 11a1.7 1.7 0 0 0-.34-1.88L9 9.06l1.41-1.41.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 13.38 6V5h2v1a1.7 1.7 0 0 0 1.03 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06 1.41 1.41-.06.06A1.7 1.7 0 0 0 19.4 11a1.7 1.7 0 0 0 1.56 1.03h.84v2h-.84A1.7 1.7 0 0 0 19.4 15Z",
  help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-1-6h2m-2-2.5c0-1.7 2.5-1.7 2.5-3.4A2.5 2.5 0 0 0 8.9 8.2",
  "book-open": "M3 5.5A2.5 2.5 0 0 1 5.5 3H11v16H5.5A2.5 2.5 0 0 0 3 21V5.5Zm18 0A2.5 2.5 0 0 0 18.5 3H13v16h5.5A2.5 2.5 0 0 1 21 21V5.5Z",
  book: "M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 0-2 2V4Zm0 0a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h14",
  "chevron-down": "m6 9 6 6 6-6",
  "chevron-right": "m9 6 6 6-6 6",
  "arrow-right": "M4 12h16m-6-6 6 6-6 6",
  "arrow-up-right": "M7 17 17 7m-8 0h8v8",
  check: "m5 12 4 4L19 6",
  "check-circle": "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-13-1 3 3 5-6",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-14v5l3 2",
  spark: "m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Zm6 13 .7 2.3L21 19l-2.3.7L18 22l-.7-2.3L15 19l2.3-.7L18 16Z",
  file: "M6 3h8l4 4v14H6V3Zm8 0v5h4M9 13h6m-6 4h6",
  send: "m21 3-7.5 18-3.2-7.3L3 10.5 21 3Zm-10.7 10.7L21 3",
  info: "M12 17v-5m0-4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  filter: "M4 5h16M7 12h10m-7 7h4",
  plus: "M12 5v14m-7-7h14",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  close: "m6 6 12 12M18 6 6 18",
  alert: "M12 9v4m0 3h.01M10.3 3.9 2.4 17.1A2 2 0 0 0 4.1 20h15.8a2 2 0 0 0 1.7-2.9L13.7 3.9a2 2 0 0 0-3.4 0Z",
  shield: "M12 3 4 6.2v5.3c0 4.9 3.4 9.2 8 10.5 4.6-1.3 8-5.6 8-10.5V6.2L12 3Z",
  bell: "M18 9a6 6 0 1 0-12 0c0 5-2 6.5-2 6.5h16S18 14 18 9Zm-4.3 10.5a2 2 0 0 1-3.4 0",
  download: "M12 3v12m0 0-4.5-4.5M12 15l4.5-4.5M4 20h16",
  trash: "M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13",
  "log-out": "M15 12H4m11 0-3.5-3.5M15 12l-3.5 3.5M9 4h9a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H9",
  lock: "M6 11h12v9H6v-9Zm2.5 0V7.5a3.5 3.5 0 1 1 7 0V11",
};

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return <svg aria-hidden="true" className="icon" fill="none" height={size} viewBox="0 0 24 24" width={size} xmlns="http://www.w3.org/2000/svg"><path d={paths[name]} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>;
}
