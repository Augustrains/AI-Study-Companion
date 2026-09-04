import { test } from "node:test";
import assert from "node:assert/strict";
import { communityReducer, communityStorageKey, emptyCommunityState, loadCommunityState, parseCommunityState, saveCommunityState } from "../src/data/communityState.ts";

const post = { id: "local-one", authorId: "tester", authorName: "学习者", category: "学习分享", course: "机器学习", title: "学习笔记", body: "今天理解了过拟合。", createdAt: "2026-09-03T09:00:00Z", likes: 0 };
const comment = { id: "comment-one", postId: "seed-1", authorName: "学习者", body: "一起讨论！" };
const memoryStorage = () => {
  const values = new Map();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), values };
};

test("empty state and missing storage are safe", () => {
  assert.deepEqual(parseCommunityState(null), emptyCommunityState());
  assert.deepEqual(loadCommunityState("no-storage"), emptyCommunityState());
});
test("corrupt, old-version and malformed snapshots reset safely", () => {
  for (const raw of ["{", "null", "[]", "{}", JSON.stringify({ ...emptyCommunityState(), version: 2 }), JSON.stringify({ ...emptyCommunityState(), likedIds: [null] }), JSON.stringify({ ...emptyCommunityState(), comments: [{ body: "bad" }] }), JSON.stringify({ ...emptyCommunityState(), posts: [{ ...post, createdAt: "not a date" }] })]) {
    assert.deepEqual(parseCommunityState(raw), emptyCommunityState());
  }
});
for (const field of ["likedIds", "savedIds", "followedIds", "joinedIds"]) {
  test(`${field}: reversible toggle, no seed mutation`, () => {
    const before = emptyCommunityState();
    const after = communityReducer(before, { type: "toggle", field, id: "seed-1" });
    assert.deepEqual(before[field], []);
    assert.deepEqual(after[field], ["seed-1"]);
    assert.deepEqual(communityReducer(after, { type: "toggle", field, id: "seed-1" })[field], []);
  });
}
test("new posts are prepended and duplicate IDs ignored", () => {
  const first = communityReducer(emptyCommunityState(), { type: "post", post });
  const second = communityReducer(first, { type: "post", post: { ...post, id: "local-two" } });
  assert.deepEqual(second.posts.map((p) => p.id), ["local-two", "local-one"]);
  assert.equal(communityReducer(first, { type: "post", post }).posts.length, 1);
});
test("invalid or whitespace content is rejected", () => {
  for (const invalid of [{ ...post, title: "  " }, { ...post, body: "" }, { ...post, body: "x".repeat(1201) }, { ...post, category: "invalid" }]) {
    assert.equal(communityReducer(emptyCommunityState(), { type: "post", post: invalid }).posts.length, 0);
  }
  assert.equal(communityReducer(emptyCommunityState(), { type: "comment", comment: { ...comment, body: " " } }).comments.length, 0);
});
test("comments stay attached to the correct post", () => {
  const state = communityReducer(emptyCommunityState(), { type: "comment", comment });
  assert.equal(state.comments[0].postId, "seed-1");
  assert.equal(communityReducer(state, { type: "comment", comment }).comments.length, 1);
});
test("snapshot round-trip preserves all interactions", () => {
  const state = { ...emptyCommunityState(), posts: [post], comments: [comment], likedIds: ["seed-1"], savedIds: ["seed-2"], followedIds: ["demo-mu"], joinedIds: ["group-ml"] };
  assert.deepEqual(parseCommunityState(JSON.stringify(state)), state);
});
test("duplicate reaction IDs are normalized", () => {
  assert.deepEqual(parseCommunityState(JSON.stringify({ ...emptyCommunityState(), likedIds: ["a", "a"] })).likedIds, ["a"]);
});
test("per-user persistence never writes learning/profile keys", () => {
  const storage = memoryStorage();
  storage.setItem("study-companion.goal.user-a", "untouched");
  const state = { ...emptyCommunityState(), posts: [post] };
  assert.equal(saveCommunityState("user-a", state, storage), true);
  assert.deepEqual(parseCommunityState(storage.getItem(communityStorageKey("user-a"))), state);
  assert.deepEqual(loadCommunityState("user-b", storage), emptyCommunityState());
  assert.equal(storage.getItem("study-companion.goal.user-a"), "untouched");
  assert.notEqual(communityStorageKey("user/a"), communityStorageKey("user%2Fa"));
});
test("blocked storage falls back to per-user session memory", () => {
  const blocked = { getItem() { throw Error("blocked"); }, setItem() { throw Error("quota"); } };
  const state = { ...emptyCommunityState(), savedIds: ["seed-1"] };
  assert.deepEqual(loadCommunityState("blocked-empty", blocked), emptyCommunityState());
  assert.equal(saveCommunityState("blocked-user", state, blocked), false);
  assert.deepEqual(loadCommunityState("blocked-user", blocked), state);
  assert.deepEqual(loadCommunityState("blocked-other", blocked), emptyCommunityState());
});
test("reset clears only the current community snapshot", () => {
  const storage = memoryStorage();
  const changed = { ...emptyCommunityState(), posts: [post], comments: [comment], likedIds: ["seed-1"] };
  saveCommunityState("reset-other", changed, storage);
  const reset = communityReducer(changed, { type: "reset" });
  saveCommunityState("reset-current", reset, storage);
  assert.deepEqual(reset, emptyCommunityState());
  assert.deepEqual(loadCommunityState("reset-other", storage), changed);
});
test("history limits keep local demo storage bounded", () => {
  let state = emptyCommunityState();
  for (let i = 0; i < 105; i++) state = communityReducer(state, { type: "post", post: { ...post, id: `p-${i}` } });
  for (let i = 0; i < 505; i++) state = communityReducer(state, { type: "comment", comment: { ...comment, id: `c-${i}` } });
  assert.equal(state.posts.length, 100);
  assert.equal(state.comments.length, 500);
  assert.deepEqual(parseCommunityState(JSON.stringify(state)), state);
});
