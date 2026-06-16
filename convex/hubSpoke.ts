import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

// Hub & Spoke Answer Capture — queries and mutations.
// Public identity uses hubId / questionId; Convex _ids are never exposed.

const hubValidator = v.object({
  hubId: v.string(),
  hubName: v.string(),
  description: v.string(),
  sortOrder: v.number(),
  createdAt: v.string(),
  updatedAt: v.string(),
});

const questionValidator = v.object({
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
});

function stripDoc<T extends { _id: unknown; _creationTime: unknown }>(
  doc: T,
): Omit<T, "_id" | "_creationTime"> {
  const { _id, _creationTime, ...rest } = doc;
  return rest;
}

function sortBySortOrder<T extends { sortOrder: number }>(items: T[]): T[] {
  return [...items].sort((a, b) => a.sortOrder - b.sortOrder);
}

async function getHubMap(ctx: { db: any }) {
  const hubs = await ctx.db.query("hubs").collect();
  const map = new Map<string, (typeof hubs)[0]>();
  for (const h of hubs) map.set(h.hubId, h);
  return map;
}

function questionMatchesHub(
  q: { primaryHubId: string; secondaryHubIds: string[] },
  hubId: string,
) {
  return (
    q.primaryHubId === hubId || (q.secondaryHubIds ?? []).includes(hubId)
  );
}

function deriveStatus(answer: string): "answered" | "unanswered" {
  return answer.trim() ? "answered" : "unanswered";
}

const DEFAULT_LOCK_TIMEOUT_MINUTES = 5;

function nowIso(): string {
  return new Date().toISOString();
}

function lockExpiresFromNow(minutes: number): string {
  return new Date(Date.now() + minutes * 60 * 1000).toISOString();
}

function isLockExpired(
  hub: { lockExpiresAt?: string },
  now: string = nowIso(),
): boolean {
  if (!hub.lockExpiresAt) return true;
  return now > hub.lockExpiresAt;
}

function isHubLockAvailable(
  hub: {
    lockStatus?: string;
    lockedBySessionId?: string;
    lockExpiresAt?: string;
  },
  sessionId: string,
  now: string = nowIso(),
): boolean {
  if (hub.lockStatus !== "locked") return true;
  if (hub.lockedBySessionId === sessionId) return true;
  return isLockExpired(hub, now);
}

const LOCK_CLEAR_PATCH = {
  lockStatus: undefined,
  lockedBySessionId: undefined,
  lockedByLabel: undefined,
  lockedAt: undefined,
  lockHeartbeatAt: undefined,
  lockExpiresAt: undefined,
} as const;

async function computeProgress(ctx: { db: any }) {
  const hubs = sortBySortOrder(await ctx.db.query("hubs").collect());
  const questions = await ctx.db.query("questions").collect();
  const totalQuestions = questions.length;
  const answeredQuestions = questions.filter(
    (q) => q.status === "answered",
  ).length;
  const unansweredQuestions = totalQuestions - answeredQuestions;
  const percentComplete =
    totalQuestions === 0
      ? 0
      : Math.round((answeredQuestions / totalQuestions) * 1000) / 10;
  const nextQuestionNumber =
    unansweredQuestions > 0 ? answeredQuestions + 1 : totalQuestions;

  const perHub = hubs.map((hub) => {
    const hubQuestions = questions.filter((q) =>
      questionMatchesHub(q, hub.hubId),
    );
    const answered = hubQuestions.filter((q) => q.status === "answered").length;
    return {
      hubId: hub.hubId,
      hubName: hub.hubName,
      total: hubQuestions.length,
      answered,
      unanswered: hubQuestions.length - answered,
    };
  });

  return {
    totalQuestions,
    answeredQuestions,
    unansweredQuestions,
    nextQuestionNumber,
    percentComplete,
    perHub,
  };
}

async function getNextUnansweredQuestionForHub(
  ctx: { db: any },
  hubId: string,
) {
  const questions = await ctx.db.query("questions").collect();
  const matching = sortBySortOrder(
    questions.filter(
      (q) => questionMatchesHub(q, hubId) && q.status === "unanswered",
    ),
  );
  return matching[0] ?? null;
}

async function hubHasUnansweredQuestions(ctx: { db: any }, hubId: string) {
  const next = await getNextUnansweredQuestionForHub(ctx, hubId);
  return next !== null;
}

async function releaseExpiredHubLocks(ctx: { db: any }) {
  const now = nowIso();
  const hubs = await ctx.db.query("hubs").collect();
  let cleared = 0;
  for (const hub of hubs) {
    if (
      hub.lockStatus === "locked" &&
      hub.lockExpiresAt &&
      now > hub.lockExpiresAt
    ) {
      await ctx.db.patch(hub._id, {
        ...LOCK_CLEAR_PATCH,
        updatedAt: now,
      });
      cleared += 1;
    }
  }
  return cleared;
}

// ------------------------------------------------------------------ queries

export const listHubs = query({
  args: {},
  handler: async (ctx) => {
    const hubs = await ctx.db.query("hubs").collect();
    return sortBySortOrder(hubs).map(stripDoc);
  },
});

export const listQuestions = query({
  args: {},
  handler: async (ctx) => {
    const questions = await ctx.db.query("questions").collect();
    return sortBySortOrder(questions).map(stripDoc);
  },
});

export const listQuestionsByHub = query({
  args: { hubId: v.string() },
  handler: async (ctx, { hubId }) => {
    const questions = await ctx.db.query("questions").collect();
    const matching = questions.filter((q) => questionMatchesHub(q, hubId));
    return sortBySortOrder(matching).map(stripDoc);
  },
});

export const listUnansweredQuestions = query({
  args: {},
  handler: async (ctx) => {
    const hubMap = await getHubMap(ctx);
    const questions = await ctx.db
      .query("questions")
      .withIndex("by_status", (q) => q.eq("status", "unanswered"))
      .collect();
    questions.sort((a, b) => {
      const hubA = hubMap.get(a.primaryHubId)?.sortOrder ?? 9999;
      const hubB = hubMap.get(b.primaryHubId)?.sortOrder ?? 9999;
      if (hubA !== hubB) return hubA - hubB;
      return a.sortOrder - b.sortOrder;
    });
    return questions.map(stripDoc);
  },
});

export const getQuestion = query({
  args: { questionId: v.string() },
  handler: async (ctx, { questionId }) => {
    const doc = await ctx.db
      .query("questions")
      .withIndex("by_question_id", (q) => q.eq("questionId", questionId))
      .unique();
    if (!doc) return null;
    return stripDoc(doc);
  },
});

export const getProgress = query({
  args: {},
  handler: async (ctx) => computeProgress(ctx),
});

export const getNextUnansweredQuestionForHubQuery = query({
  args: { hubId: v.string() },
  handler: async (ctx, { hubId }) => {
    const doc = await getNextUnansweredQuestionForHub(ctx, hubId);
    if (!doc) return null;
    return stripDoc(doc);
  },
});

export const listHubLockStatuses = query({
  args: {},
  handler: async (ctx) => {
    const now = nowIso();
    const hubs = sortBySortOrder(await ctx.db.query("hubs").collect());
    const questions = await ctx.db.query("questions").collect();

    return hubs.map((hub) => {
      const hubQuestions = questions.filter((q) =>
        questionMatchesHub(q, hub.hubId),
      );
      const answered = hubQuestions.filter((q) => q.status === "answered").length;
      const unanswered = hubQuestions.length - answered;
      const isStale =
        hub.lockStatus === "locked" && isLockExpired(hub, now);
      return {
        hubId: hub.hubId,
        hubName: hub.hubName,
        lockStatus: hub.lockStatus ?? "unlocked",
        lockedBySessionId: hub.lockedBySessionId,
        lockedByLabel: hub.lockedByLabel,
        lockExpiresAt: hub.lockExpiresAt,
        isStale,
        answered,
        unanswered,
        total: hubQuestions.length,
      };
    });
  },
});

export const exportData = query({
  args: { selectedHubIds: v.optional(v.array(v.string())) },
  handler: async (ctx, { selectedHubIds }) => {
    const allHubs = sortBySortOrder(await ctx.db.query("hubs").collect());
    const allQuestions = await ctx.db.query("questions").collect();
    const hubIds =
      selectedHubIds && selectedHubIds.length > 0
        ? new Set(selectedHubIds)
        : null;

    const hubs = hubIds
      ? allHubs.filter((h) => hubIds.has(h.hubId))
      : allHubs;

    return hubs.map((hub) => {
      const hubQuestions = sortBySortOrder(
        allQuestions.filter((q) => questionMatchesHub(q, hub.hubId)),
      );
      return {
        hubId: hub.hubId,
        hubName: hub.hubName,
        description: hub.description,
        sortOrder: hub.sortOrder,
        questions: hubQuestions.map((q) => ({
          questionId: q.questionId,
          question: q.question,
          answer: q.answer,
          status: q.status,
          notes: q.notes,
          primaryHubId: q.primaryHubId,
          secondaryHubIds: q.secondaryHubIds,
          sortOrder: q.sortOrder,
          updatedAt: q.updatedAt,
          answeredAt: q.answeredAt,
          answeredBy: q.answeredBy,
        })),
      };
    });
  },
});

// ---------------------------------------------------------------- mutations

async function upsertByIndex(
  ctx: { db: any },
  table: "hubs" | "questions",
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

export const upsertHub = mutation({
  args: { hub: hubValidator },
  handler: async (ctx, { hub }) => {
    const existing = await ctx.db
      .query("hubs")
      .withIndex("by_hub_id", (q) => q.eq("hubId", hub.hubId))
      .unique();
    const record = existing
      ? {
          ...hub,
          createdAt: existing.createdAt,
          lockStatus: existing.lockStatus,
          lockedBySessionId: existing.lockedBySessionId,
          lockedByLabel: existing.lockedByLabel,
          lockedAt: existing.lockedAt,
          lockHeartbeatAt: existing.lockHeartbeatAt,
          lockExpiresAt: existing.lockExpiresAt,
        }
      : hub;
    const result = await upsertByIndex(
      ctx,
      "hubs",
      "by_hub_id",
      "hubId",
      record,
    );
    return { result, hubId: hub.hubId };
  },
});

export const upsertQuestion = mutation({
  args: {
    question: questionValidator,
    preserveAnswer: v.optional(v.boolean()),
  },
  handler: async (ctx, { question, preserveAnswer }) => {
    const shouldPreserve = preserveAnswer !== false;
    const existing = await ctx.db
      .query("questions")
      .withIndex("by_question_id", (q) =>
        q.eq("questionId", question.questionId),
      )
      .unique();

    let record = { ...question };
    if (existing) {
      record.createdAt = existing.createdAt;
      if (shouldPreserve && existing.answer.trim()) {
        record = {
          ...record,
          answer: existing.answer,
          status: existing.status,
          answeredAt: existing.answeredAt,
          answeredBy: existing.answeredBy,
        };
      } else {
        record.status = deriveStatus(record.answer);
      }
    } else {
      record.status = deriveStatus(record.answer);
    }

    const result = await upsertByIndex(
      ctx,
      "questions",
      "by_question_id",
      "questionId",
      record,
    );
    return { result, questionId: question.questionId };
  },
});

export const saveAnswer = mutation({
  args: {
    questionId: v.string(),
    answer: v.string(),
    answeredBy: v.optional(v.string()),
  },
  handler: async (ctx, { questionId, answer, answeredBy }) => {
    const doc = await ctx.db
      .query("questions")
      .withIndex("by_question_id", (q) => q.eq("questionId", questionId))
      .unique();
    if (!doc) throw new Error(`Question not found: ${questionId}`);

    const now = new Date().toISOString();
    const trimmed = answer.trim();
    const status = deriveStatus(answer);
    const patch: Record<string, unknown> = {
      answer,
      status,
      updatedAt: now,
    };
    if (trimmed) {
      patch.answeredAt = now;
      if (answeredBy) patch.answeredBy = answeredBy;
    }

    await ctx.db.patch(doc._id, patch);
    const updated = await ctx.db.get(doc._id);
    if (!updated) throw new Error("Failed to load updated question");
    return stripDoc(updated);
  },
});

export const updateQuestionNotes = mutation({
  args: { questionId: v.string(), notes: v.string() },
  handler: async (ctx, { questionId, notes }) => {
    const doc = await ctx.db
      .query("questions")
      .withIndex("by_question_id", (q) => q.eq("questionId", questionId))
      .unique();
    if (!doc) throw new Error(`Question not found: ${questionId}`);
    const now = new Date().toISOString();
    await ctx.db.patch(doc._id, { notes, updatedAt: now });
    const updated = await ctx.db.get(doc._id);
    if (!updated) throw new Error("Failed to load updated question");
    return stripDoc(updated);
  },
});

export const resetAnswer = mutation({
  args: { questionId: v.string() },
  handler: async (ctx, { questionId }) => {
    const doc = await ctx.db
      .query("questions")
      .withIndex("by_question_id", (q) => q.eq("questionId", questionId))
      .unique();
    if (!doc) throw new Error(`Question not found: ${questionId}`);

    const now = new Date().toISOString();
    await ctx.db.patch(doc._id, {
      answer: "",
      status: "unanswered",
      updatedAt: now,
      answeredAt: undefined,
      answeredBy: undefined,
    });
    const updated = await ctx.db.get(doc._id);
    if (!updated) throw new Error("Failed to load updated question");
    return stripDoc(updated);
  },
});

// ---------------------------------------------------------------- hub locks

export const releaseExpiredHubLocksMutation = mutation({
  args: {},
  handler: async (ctx) => {
    const cleared = await releaseExpiredHubLocks(ctx);
    return { cleared };
  },
});

export const claimNextAvailableHub = mutation({
  args: {
    sessionId: v.string(),
    lockedByLabel: v.optional(v.string()),
    lockTimeoutMinutes: v.optional(v.number()),
  },
  handler: async (ctx, { sessionId, lockedByLabel, lockTimeoutMinutes }) => {
    await releaseExpiredHubLocks(ctx);

    const timeoutMinutes = lockTimeoutMinutes ?? DEFAULT_LOCK_TIMEOUT_MINUTES;
    const now = nowIso();
    const expiresAt = lockExpiresFromNow(timeoutMinutes);
    const hubs = sortBySortOrder(await ctx.db.query("hubs").collect());

    // Reclaim an existing lock held by this session before claiming a new hub.
    for (const hub of hubs) {
      const fresh = await ctx.db.get(hub._id);
      if (!fresh || fresh.lockedBySessionId !== sessionId) continue;

      const hasUnanswered = await hubHasUnansweredQuestions(ctx, fresh.hubId);
      if (!hasUnanswered) {
        if (fresh.lockStatus === "locked") {
          await ctx.db.patch(fresh._id, { ...LOCK_CLEAR_PATCH, updatedAt: now });
        }
        continue;
      }

      await ctx.db.patch(fresh._id, {
        lockStatus: "locked",
        lockedBySessionId: sessionId,
        lockedByLabel: lockedByLabel ?? fresh.lockedByLabel ?? `Session ${sessionId.slice(0, 8)}`,
        lockedAt: fresh.lockedAt ?? now,
        lockHeartbeatAt: now,
        lockExpiresAt: expiresAt,
        updatedAt: now,
      });

      const claimed = await ctx.db.get(fresh._id);
      if (!claimed) break;

      const firstQuestion = await getNextUnansweredQuestionForHub(
        ctx,
        claimed.hubId,
      );
      const progress = await computeProgress(ctx);
      return {
        claimed: true,
        hub: stripDoc(claimed),
        firstQuestion: firstQuestion ? stripDoc(firstQuestion) : null,
        progress,
        reclaimed: true,
      };
    }

    for (const hub of hubs) {
      const hasUnanswered = await hubHasUnansweredQuestions(ctx, hub.hubId);
      if (!hasUnanswered) continue;

      const fresh = await ctx.db.get(hub._id);
      if (!fresh) continue;
      if (!isHubLockAvailable(fresh, sessionId, now)) continue;

      await ctx.db.patch(fresh._id, {
        lockStatus: "locked",
        lockedBySessionId: sessionId,
        lockedByLabel: lockedByLabel ?? `Session ${sessionId.slice(0, 8)}`,
        lockedAt: now,
        lockHeartbeatAt: now,
        lockExpiresAt: expiresAt,
        updatedAt: now,
      });

      const claimed = await ctx.db.get(fresh._id);
      if (!claimed) {
        return {
          claimed: false,
          message: "Failed to claim hub after lock assignment.",
        };
      }

      const firstQuestion = await getNextUnansweredQuestionForHub(
        ctx,
        claimed.hubId,
      );
      const progress = await computeProgress(ctx);

      return {
        claimed: true,
        hub: stripDoc(claimed),
        firstQuestion: firstQuestion ? stripDoc(firstQuestion) : null,
        progress,
      };
    }

    const progress = await computeProgress(ctx);
    return {
      claimed: false,
      message: "No eligible hubs with unanswered questions are available.",
      progress,
    };
  },
});

export const renewHubLock = mutation({
  args: {
    hubId: v.string(),
    sessionId: v.string(),
    lockTimeoutMinutes: v.optional(v.number()),
  },
  handler: async (ctx, { hubId, sessionId, lockTimeoutMinutes }) => {
    const doc = await ctx.db
      .query("hubs")
      .withIndex("by_hub_id", (q) => q.eq("hubId", hubId))
      .unique();
    if (!doc) return { success: false, reason: "hub_not_found" };
    if (doc.lockedBySessionId !== sessionId) {
      return { success: false, reason: "not_owner" };
    }

    const timeoutMinutes = lockTimeoutMinutes ?? DEFAULT_LOCK_TIMEOUT_MINUTES;
    const now = nowIso();
    await ctx.db.patch(doc._id, {
      lockHeartbeatAt: now,
      lockExpiresAt: lockExpiresFromNow(timeoutMinutes),
      updatedAt: now,
    });
    return { success: true };
  },
});

export const releaseHubLock = mutation({
  args: { hubId: v.string(), sessionId: v.string() },
  handler: async (ctx, { hubId, sessionId }) => {
    const doc = await ctx.db
      .query("hubs")
      .withIndex("by_hub_id", (q) => q.eq("hubId", hubId))
      .unique();
    if (!doc) return { success: false, reason: "hub_not_found" };
    if (doc.lockStatus === "locked" && doc.lockedBySessionId !== sessionId) {
      return { success: false, reason: "not_owner" };
    }

    const now = nowIso();
    await ctx.db.patch(doc._id, {
      ...LOCK_CLEAR_PATCH,
      updatedAt: now,
    });
    return { success: true };
  },
});
