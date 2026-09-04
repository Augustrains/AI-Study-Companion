/** Frontend-only demo state. No learner model, API, or backend writes. */
export type CommunityCategory = "学习分享" | "问题讨论" | "寻找搭子";
export const communityCategories: CommunityCategory[] = ["学习分享", "问题讨论", "寻找搭子"];
export type CommunityPost = {
  id: string; authorId: string; authorName: string; category: CommunityCategory;
  course: string; title: string; body: string; createdAt: string; likes: number;
};
export type CommunityComment = { id: string; postId: string; authorName: string; body: string };
export type CommunityState = {
  version: 1; posts: CommunityPost[]; comments: CommunityComment[];
  likedIds: string[]; savedIds: string[]; followedIds: string[]; joinedIds: string[];
};
export type CommunityAction =
  | { type: "toggle"; field: "likedIds" | "savedIds" | "followedIds" | "joinedIds"; id: string }
  | { type: "post"; post: CommunityPost }
  | { type: "comment"; comment: CommunityComment }
  | { type: "reset" };

export const communityStorageKey = (userId: string) => `study-companion.community.v1.${encodeURIComponent(userId)}`;
export const emptyCommunityState = (): CommunityState => ({ version: 1, posts: [], comments: [], likedIds: [], savedIds: [], followedIds: [], joinedIds: [] });
const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isText = (value: unknown, limit: number): value is string => typeof value === "string" && value.trim().length > 0 && value.length <= limit;
const isIds = (value: unknown): value is string[] => Array.isArray(value) && value.length <= 1000 && value.every((id) => isText(id, 200));

function isPost(value: unknown): value is CommunityPost {
  if (!isObject(value)) return false;
  return isText(value.id, 200) && isText(value.authorId, 200) && isText(value.authorName, 100)
    && communityCategories.includes(value.category as CommunityCategory) && isText(value.course, 80)
    && isText(value.title, 96) && isText(value.body, 1200) && isText(value.createdAt, 40)
    && Number.isFinite(Date.parse(value.createdAt)) && typeof value.likes === "number" && Number.isInteger(value.likes) && value.likes >= 0;
}

function isComment(value: unknown): value is CommunityComment {
  return isObject(value) && isText(value.id, 200) && isText(value.postId, 200)
    && isText(value.authorName, 100) && isText(value.body, 300);
}

/** localStorage is untrusted input: reject malformed or unsupported snapshots. */
export function parseCommunityState(raw: string | null): CommunityState {
  if (!raw) return emptyCommunityState();
  try {
    const value: unknown = JSON.parse(raw);
    if (!isObject(value) || value.version !== 1 || !Array.isArray(value.posts) || value.posts.length > 100
      || !value.posts.every(isPost) || !Array.isArray(value.comments) || value.comments.length > 500
      || !value.comments.every(isComment) || !isIds(value.likedIds) || !isIds(value.savedIds)
      || !isIds(value.followedIds) || !isIds(value.joinedIds)) return emptyCommunityState();
    return {
      version: 1, posts: value.posts, comments: value.comments,
      likedIds: [...new Set(value.likedIds)], savedIds: [...new Set(value.savedIds)],
      followedIds: [...new Set(value.followedIds)], joinedIds: [...new Set(value.joinedIds)],
    };
  } catch { return emptyCommunityState(); }
}

export function communityReducer(state: CommunityState, action: CommunityAction): CommunityState {
  if (action.type === "reset") return emptyCommunityState();
  if (action.type === "toggle") {
    const ids = state[action.field];
    if (!isText(action.id, 200)) return state;
    return { ...state, [action.field]: ids.includes(action.id) ? ids.filter((id) => id !== action.id) : [...ids, action.id].slice(-1000) };
  }
  if (action.type === "post") {
    if (!isPost(action.post) || state.posts.some((post) => post.id === action.post.id)) return state;
    return { ...state, posts: [action.post, ...state.posts].slice(0, 100) };
  }
  if (!isComment(action.comment) || state.comments.some((comment) => comment.id === action.comment.id)) return state;
  return { ...state, comments: [...state.comments, action.comment].slice(-500) };
}

// Preserve session interactions if storage is unavailable (private mode/quota).
const memoryStates = new Map<string, CommunityState>();
type StorageReader = Pick<Storage, "getItem">;
type StorageWriter = Pick<Storage, "setItem">;
export function loadCommunityState(userId: string, storage?: StorageReader): CommunityState {
  const key = communityStorageKey(userId);
  if (memoryStates.has(key)) return memoryStates.get(key)!;
  try { return parseCommunityState(storage?.getItem(key) ?? null); }
  catch { return emptyCommunityState(); }
}
export function saveCommunityState(userId: string, state: CommunityState, storage?: StorageWriter): boolean {
  const key = communityStorageKey(userId);
  memoryStates.set(key, state);
  try {
    if (!storage) return false;
    storage.setItem(key, JSON.stringify(state));
    return true;
  } catch { return false; }
}
