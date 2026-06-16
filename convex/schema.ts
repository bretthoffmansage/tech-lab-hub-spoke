import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

// Hosted data for the Tech Lab Transcript Intelligence demo.
// External IDs (chunkId, recordId, assetId, topicKey) are the public
// identity; Convex _ids are never exposed. Irregular/nested shapes from the
// local pipeline live in fullRecord/pack as v.any().

export default defineSchema({
  transcriptChunks: defineTable({
    chunkId: v.string(),
    sourceFile: v.string(),
    cleanedFile: v.optional(v.string()),
    transcriptTitle: v.string(),
    inferredDate: v.optional(v.string()),
    chunkIndex: v.number(),
    wordCount: v.optional(v.number()),
    text: v.string(),
    fullRecord: v.optional(v.any()),
  })
    .index("by_chunk_id", ["chunkId"])
    .index("by_source_file", ["sourceFile"])
    .index("by_transcript_title", ["transcriptTitle"])
    .searchIndex("search_text", {
      searchField: "text",
      filterFields: ["sourceFile", "transcriptTitle"],
    }),

  marketingInsights: defineTable({
    recordId: v.string(),
    chunkId: v.string(),
    sourceFile: v.string(),
    cleanedFile: v.optional(v.string()),
    transcriptTitle: v.string(),
    inferredDate: v.optional(v.string()),
    chunkIndex: v.number(),
    coreTopic: v.optional(v.string()),
    usefulnessScore: v.optional(v.number()),
    confidenceScore: v.optional(v.number()),
    extractionProvider: v.optional(v.string()),
    extractionModel: v.optional(v.string()),
    tags: v.optional(v.array(v.string())),
    fullRecord: v.any(),
  })
    .index("by_record_id", ["recordId"])
    .index("by_chunk_id", ["chunkId"])
    .index("by_source_file", ["sourceFile"])
    .index("by_provider", ["extractionProvider"]),

  marketingAssets: defineTable({
    assetId: v.string(),
    recordId: v.string(),
    chunkId: v.string(),
    sourceFile: v.string(),
    transcriptTitle: v.string(),
    inferredDate: v.optional(v.string()),
    assetType: v.string(),
    assetText: v.string(),
    usefulnessScore: v.optional(v.number()),
    confidenceScore: v.optional(v.number()),
    tags: v.optional(v.array(v.string())),
    topicKeys: v.optional(v.array(v.string())),
    fullRecord: v.optional(v.any()),
  })
    .index("by_asset_id", ["assetId"])
    .index("by_record_id", ["recordId"])
    .index("by_chunk_id", ["chunkId"])
    .index("by_asset_type", ["assetType"])
    .searchIndex("search_asset_text", {
      searchField: "assetText",
      filterFields: ["assetType"],
    }),

  topicIndex: defineTable({
    topicKey: v.string(),
    displayName: v.string(),
    matchingChunks: v.number(),
    sourceFilesCount: v.optional(v.number()),
    topAssetTypes: v.optional(v.any()),
    relatedTerms: v.optional(v.any()),
    isWeakTopic: v.optional(v.boolean()),
    fullRecord: v.any(),
  }).index("by_topic_key", ["topicKey"]),

  topicPacks: defineTable({
    topicKey: v.string(),
    displayName: v.string(),
    pack: v.any(),
    generatedAt: v.optional(v.string()),
    extractionMode: v.optional(v.string()),
    stats: v.optional(v.any()),
  }).index("by_topic_key", ["topicKey"]),

  appMetadata: defineTable({
    key: v.string(),
    value: v.any(),
    updatedAt: v.string(),
  }).index("by_key", ["key"]),

  // Hub & Spoke Answer Capture — stable public IDs (hubId, questionId).
  hubs: defineTable({
    hubId: v.string(),
    hubName: v.string(),
    description: v.string(),
    sortOrder: v.number(),
    createdAt: v.string(),
    updatedAt: v.string(),
    lockStatus: v.optional(v.string()),
    lockedBySessionId: v.optional(v.string()),
    lockedByLabel: v.optional(v.string()),
    lockedAt: v.optional(v.string()),
    lockHeartbeatAt: v.optional(v.string()),
    lockExpiresAt: v.optional(v.string()),
  })
    .index("by_hub_id", ["hubId"])
    .index("by_sort_order", ["sortOrder"]),

  questions: defineTable({
    questionId: v.string(),
    question: v.string(),
    answer: v.string(),
    status: v.string(),
    primaryHubId: v.string(),
    secondaryHubIds: v.array(v.string()),
    notes: v.optional(v.string()),
    sortOrder: v.number(),
    createdAt: v.string(),
    updatedAt: v.string(),
    answeredAt: v.optional(v.string()),
    answeredBy: v.optional(v.string()),
  })
    .index("by_question_id", ["questionId"])
    .index("by_primary_hub", ["primaryHubId"])
    .index("by_status", ["status"])
    .index("by_sort_order", ["sortOrder"])
    .index("by_primary_hub_and_sort_order", ["primaryHubId", "sortOrder"]),
});
