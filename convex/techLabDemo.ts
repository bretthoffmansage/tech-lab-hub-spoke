import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

// Queries and idempotent upsert mutations for the Tech Lab demo.
// Upserts key on external IDs (chunkId / recordId / assetId / topicKey),
// so re-running the upload script updates records instead of duplicating.

// ------------------------------------------------------------------ queries

export const getTopics = query({
  args: {},
  handler: async (ctx) => {
    const topics = await ctx.db.query("topicIndex").collect();
    topics.sort((a, b) => b.matchingChunks - a.matchingChunks);
    return topics.map(({ _id, _creationTime, ...rest }) => rest);
  },
});

export const getTopicByKey = query({
  args: { topicKey: v.string() },
  handler: async (ctx, { topicKey }) => {
    const doc = await ctx.db
      .query("topicIndex")
      .withIndex("by_topic_key", (q) => q.eq("topicKey", topicKey))
      .unique();
    if (!doc) return null;
    const { _id, _creationTime, ...rest } = doc;
    return rest;
  },
});

export const getTopicPack = query({
  args: { topicKey: v.string() },
  handler: async (ctx, { topicKey }) => {
    const doc = await ctx.db
      .query("topicPacks")
      .withIndex("by_topic_key", (q) => q.eq("topicKey", topicKey))
      .unique();
    if (!doc) return null;
    const { _id, _creationTime, ...rest } = doc;
    return rest;
  },
});

export const getTopicPacks = query({
  args: {},
  handler: async (ctx) => {
    const docs = await ctx.db.query("topicPacks").collect();
    // listing only — the packs themselves can be large, fetch one by key
    return docs.map((d) => ({
      topicKey: d.topicKey,
      displayName: d.displayName,
      generatedAt: d.generatedAt,
      extractionMode: d.extractionMode,
      stats: d.stats,
    }));
  },
});

export const getAssetsByTopic = query({
  args: {
    topicKey: v.string(),
    assetType: v.optional(v.string()),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, { topicKey, assetType, limit }) => {
    const max = Math.min(limit ?? 25, 200);
    // topicKeys is an array field, which Convex indexes can't filter on
    // directly. Assets are small, so we scan the (optionally type-narrowed)
    // table and filter in JS — fine at demo scale (~5k docs). If topicKeys
    // were never populated, callers should fall back to topic pack sections.
    const base = assetType
      ? ctx.db
          .query("marketingAssets")
          .withIndex("by_asset_type", (q) => q.eq("assetType", assetType))
      : ctx.db.query("marketingAssets");
    const docs = await base.collect();
    const matching = docs.filter((d) => (d.topicKeys ?? []).includes(topicKey));
    matching.sort(
      (a, b) =>
        (b.usefulnessScore ?? 0) - (a.usefulnessScore ?? 0) ||
        (b.confidenceScore ?? 0) - (a.confidenceScore ?? 0),
    );
    return matching
      .slice(0, max)
      .map(({ _id, _creationTime, fullRecord, ...rest }) => rest);
  },
});

export const searchTranscriptChunks = query({
  args: { query: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, args) => {
    const max = Math.min(args.limit ?? 10, 50);
    const docs = await ctx.db
      .query("transcriptChunks")
      .withSearchIndex("search_text", (q) => q.search("text", args.query))
      .take(max);
    return docs.map(({ _id, _creationTime, fullRecord, ...rest }) => rest);
  },
});

export const searchMarketingAssets = query({
  args: {
    query: v.string(),
    assetType: v.optional(v.string()),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const max = Math.min(args.limit ?? 10, 100);
    const docs = await ctx.db
      .query("marketingAssets")
      .withSearchIndex("search_asset_text", (q) => {
        const s = q.search("assetText", args.query);
        return args.assetType ? s.eq("assetType", args.assetType) : s;
      })
      .take(max);
    return docs.map(({ _id, _creationTime, fullRecord, ...rest }) => rest);
  },
});

export const getChunkById = query({
  args: { chunkId: v.string() },
  handler: async (ctx, { chunkId }) => {
    const doc = await ctx.db
      .query("transcriptChunks")
      .withIndex("by_chunk_id", (q) => q.eq("chunkId", chunkId))
      .unique();
    if (!doc) return null;
    const { _id, _creationTime, ...rest } = doc;
    return rest;
  },
});

export const getAppMetadata = query({
  args: {},
  handler: async (ctx) => {
    const docs = await ctx.db.query("appMetadata").collect();
    const out: Record<string, unknown> = {};
    for (const d of docs) out[d.key] = d.value;
    return out;
  },
});

// ---------------------------------------------------------------- mutations

async function upsertBy(
  ctx: any,
  table: string,
  index: string,
  field: string,
  record: Record<string, unknown>,
) {
  const existing = await ctx.db
    .query(table)
    .withIndex(index, (q: any) => q.eq(field, record[field]))
    .unique();
  if (existing) {
    await ctx.db.patch(existing._id, record);
    return "updated";
  }
  await ctx.db.insert(table, record);
  return "inserted";
}

export const upsertTranscriptChunk = mutation({
  args: { record: v.any() },
  handler: async (ctx, { record }) =>
    upsertBy(ctx, "transcriptChunks", "by_chunk_id", "chunkId", record),
});

export const upsertMarketingInsight = mutation({
  args: { record: v.any() },
  handler: async (ctx, { record }) =>
    upsertBy(ctx, "marketingInsights", "by_record_id", "recordId", record),
});

export const upsertMarketingAsset = mutation({
  args: { record: v.any() },
  handler: async (ctx, { record }) =>
    upsertBy(ctx, "marketingAssets", "by_asset_id", "assetId", record),
});

export const upsertTopicIndex = mutation({
  args: { record: v.any() },
  handler: async (ctx, { record }) =>
    upsertBy(ctx, "topicIndex", "by_topic_key", "topicKey", record),
});

export const upsertTopicPack = mutation({
  args: { record: v.any() },
  handler: async (ctx, { record }) =>
    upsertBy(ctx, "topicPacks", "by_topic_key", "topicKey", record),
});

export const upsertAppMetadata = mutation({
  args: { key: v.string(), value: v.any() },
  handler: async (ctx, { key, value }) => {
    const record = { key, value, updatedAt: new Date().toISOString() };
    return upsertBy(ctx, "appMetadata", "by_key", "key", record);
  },
});

// batch variants so the upload script doesn't need thousands of round trips
const BATCH_TABLES: Record<string, [string, string]> = {
  transcriptChunks: ["by_chunk_id", "chunkId"],
  marketingInsights: ["by_record_id", "recordId"],
  marketingAssets: ["by_asset_id", "assetId"],
  topicIndex: ["by_topic_key", "topicKey"],
  topicPacks: ["by_topic_key", "topicKey"],
};

export const batchUpsert = mutation({
  args: { table: v.string(), records: v.array(v.any()) },
  handler: async (ctx, { table, records }) => {
    const spec = BATCH_TABLES[table];
    if (!spec) throw new Error(`batchUpsert: unsupported table ${table}`);
    const [index, field] = spec;
    let inserted = 0;
    let updated = 0;
    for (const record of records) {
      const result = await upsertBy(ctx, table, index, field, record);
      if (result === "inserted") inserted += 1;
      else updated += 1;
    }
    return { inserted, updated };
  },
});

export const countTable = query({
  args: { table: v.string() },
  handler: async (ctx, { table }) => {
    if (!(table in BATCH_TABLES) && table !== "appMetadata") {
      throw new Error(`countTable: unsupported table ${table}`);
    }
    // demo-scale only: collect() is fine at a few thousand docs
    const docs = await (ctx.db.query as any)(table).collect();
    return docs.length;
  },
});

export const clearDemoData = mutation({
  args: { confirm: v.string() },
  handler: async (ctx, { confirm }) => {
    if (confirm !== "CLEAR_TECH_LAB_DEMO_DATA") {
      throw new Error(
        'clearDemoData requires confirm="CLEAR_TECH_LAB_DEMO_DATA"',
      );
    }
    // deletes up to 1000 docs per table per call to stay inside transaction
    // limits — re-run until it reports {remaining: 0}
    const tables = [...Object.keys(BATCH_TABLES), "appMetadata"];
    let deleted = 0;
    let remaining = 0;
    for (const table of tables) {
      const docs = await (ctx.db.query as any)(table).take(1001);
      const slice = docs.slice(0, 1000);
      for (const doc of slice) await ctx.db.delete(doc._id);
      deleted += slice.length;
      if (docs.length > 1000) remaining += 1;
    }
    return { deleted, tablesPossiblyRemaining: remaining };
  },
});
