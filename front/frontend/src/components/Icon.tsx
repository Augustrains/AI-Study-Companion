export type IconName = "home" | "target" | "calendar" | "chart" | "chat" | "user" | "settings" | "help" | "book-open" | "book" | "lock" | "chevron-down" | "chevron-right" | "arrow-right" | "arrow-up-right" | "check" | "check-circle" | "clock" | "spark" | "file" | "send" | "info" | "filter" | "plus" | "more" | "close";

const paths: Record<IconName, string> = {
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
  lock: "M7 11V8a5 5 0 0 1 10 0v3m-11 0h12v10H6V11Zm6 4v2",
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
};

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return <svg aria-hidden="true" className="icon" fill="none" height={size} viewBox="0 0 24 24" width={size} xmlns="http://www.w3.org/2000/svg"><path d={paths[name]} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>;
}
