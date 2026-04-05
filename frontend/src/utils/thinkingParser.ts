export interface ThinkingParseResult {
  reasoning: string;
  answer: string;
}

interface SplitBoundary {
  start: number;
  end: number;
}

const THOUGHT_PREFIX = /^thought\s*/i;
const STEP_LIKE_PATTERN = /(?:^|\n)\s*(?:\d{1,2}[.)]|(?:step|步骤)\s*\d+[:.)]?)\s+/gim;

const DIRECT_MARKERS: RegExp[] = [
  /this leads(?: directly)? to the detailed response provided below\.\)?/i,
  /final output generation\.?\)?/i,
  /(?:final answer|===\s*answer\s*===|最终回答|下面是(?:正式)?回答|以下是(?:详细)?回答)[:：]?/i,
];

const ANSWER_LEAD_PATTERN =
  /(?:\n|^)\s*(?:这是|下面|以下|综上|总结|结论|Sure[,，]?|Okay[,，]?|当然[,，]?|好的[,，]?|Now[,，]?|Here(?:'s| is))/m;

const HANDOFF_PATTERN =
  /\((?:self-correction|the final output structure looks good|final output generation)[^)]+\)\s*/i;

const CJK_CHAR = /[\u3400-\u9fff]/;
const REASONING_HINT_PATTERN =
  /(thinking process|analyze the request|execution\s*-?\s*target|self-correction|review and formatting|determine the|strategy|fulfilling specific requirements|core concept|develop the model structure|target \d)/i;
const ANSWER_HINT_PATTERN =
  /^(?:#{1,4}\s+|🌌|🌍|🗿|原句|第一部分|第二部分|第三部分|总结|结论|最终答案|终极答案)|(?:这是一个|以下是|下面是|原句[:：]|终极答案|跨界翻译|第一部分|第二部分|第三部分)/m;
const TABLE_HINT_PATTERN = /\|[^|\n]+\|[^|\n]+\|/;

function isCjk(char: string): boolean {
  return CJK_CHAR.test(char);
}

function cjkRatio(text: string): number {
  if (!text) {
    return 0;
  }
  const chars = Array.from(text);
  const cjkCount = chars.filter((ch) => isCjk(ch)).length;
  return cjkCount / chars.length;
}

function sanitizeAnswer(text: string): string {
  return text.replace(/^[\s:：)\].-]+/, "").trim();
}

function findDirectMarkerBoundary(raw: string): SplitBoundary | null {
  for (const pattern of DIRECT_MARKERS) {
    const match = pattern.exec(raw);
    if (match && typeof match.index === "number") {
      return { start: match.index, end: match.index + match[0].length };
    }
  }
  return null;
}

function findStructuredStepBoundary(raw: string): SplitBoundary | null {
  const matches = Array.from(raw.matchAll(STEP_LIKE_PATTERN));
  if (matches.length < 3) {
    return null;
  }

  const last = matches[matches.length - 1];
  const stepEnd = (last.index ?? 0) + last[0].length;
  const tail = raw.slice(stepEnd);
  const paragraphMatch = /\n{2,}([^\n-*\d][\s\S]*)$/m.exec(tail);
  const answerCandidate = (paragraphMatch?.[1] ?? tail).trim();

  if (answerCandidate.length < 24) {
    return null;
  }

  const answerStart = raw.indexOf(answerCandidate, stepEnd);
  if (answerStart <= 0) {
    return null;
  }

  return { start: answerStart, end: answerStart };
}

function findAnswerLeadBoundary(raw: string): SplitBoundary | null {
  const leadMatch = ANSWER_LEAD_PATTERN.exec(raw);
  if (!leadMatch || typeof leadMatch.index !== "number" || leadMatch.index <= 30) {
    return null;
  }
  const answer = raw.slice(leadMatch.index).trim();
  if (answer.length < 16) {
    return null;
  }
  return { start: leadMatch.index, end: leadMatch.index };
}

function findHandoffBoundary(raw: string): SplitBoundary | null {
  const match = HANDOFF_PATTERN.exec(raw);
  if (!match || typeof match.index !== "number") {
    return null;
  }
  const answerStart = match.index + match[0].length;
  const answer = raw.slice(answerStart).trim();
  if (answer.length < 16) {
    return null;
  }
  return { start: answerStart, end: answerStart };
}

function findLanguageShiftBoundary(raw: string): SplitBoundary | null {
  const boundaryHints = /(?:这是|由于这是|下面|以下|🌌|##\s*|###\s*)/;
  const englishReasoningHints = /(analyze|target|execution|strategy|self-correction|step|review|formatting)/i;
  const windowSize = 80;

  for (let i = windowSize; i < raw.length - windowSize; i += 1) {
    if (!isCjk(raw[i])) {
      continue;
    }
    const prev = raw.slice(i - windowSize, i);
    const next = raw.slice(i, i + windowSize);
    if (cjkRatio(prev) < 0.06 && cjkRatio(next) > 0.12) {
      const tail = raw.slice(i).trim();
      if (tail.length < 20 || !boundaryHints.test(tail)) {
        continue;
      }
      const head = raw.slice(0, i);
      if (!englishReasoningHints.test(head)) {
        continue;
      }
      return { start: i, end: i };
    }
  }

  const lines = raw.split("\n");
  let offset = 0;
  for (const line of lines) {
    const trimmed = line.trim();
    const startsWithCjk = Boolean(trimmed && isCjk(trimmed[0]));
    if (startsWithCjk && boundaryHints.test(trimmed)) {
      const head = raw.slice(0, offset);
      const tail = raw.slice(offset).trim();
      if (tail.length >= 20 && englishReasoningHints.test(head)) {
        return { start: offset, end: offset };
      }
    }
    offset += line.length + 1;
  }

  return null;
}

interface ParagraphSpan {
  text: string;
  start: number;
}

function splitParagraphs(raw: string): ParagraphSpan[] {
  const spans: ParagraphSpan[] = [];
  let i = 0;

  while (i < raw.length) {
    while (i < raw.length && raw[i] === "\n") {
      i += 1;
    }
    if (i >= raw.length) {
      break;
    }

    const start = i;
    let j = i;
    while (j < raw.length) {
      if (raw[j] !== "\n") {
        j += 1;
        continue;
      }
      let k = j;
      while (k < raw.length && raw[k] === "\n") {
        k += 1;
      }
      if (k - j >= 2) {
        break;
      }
      j += 1;
    }

    const text = raw.slice(start, j).trim();
    if (text) {
      spans.push({ text, start });
    }

    i = j;
    while (i < raw.length && raw[i] === "\n") {
      i += 1;
    }
  }

  return spans;
}

function asciiLetterCount(text: string): number {
  return (text.match(/[A-Za-z]/g) || []).length;
}

function reasoningScore(paragraph: string): number {
  let score = 0;
  const trimmed = paragraph.trim();
  const cjk = cjkRatio(trimmed);

  if (REASONING_HINT_PATTERN.test(trimmed)) {
    score += 4;
  }
  if (/^(?:\d{1,2}[.)]|(?:step|步骤)\s*\d+[:.)]?)/i.test(trimmed)) {
    score += 3;
  }
  if (/\((?:self-correction|review|thinking)\b/i.test(trimmed)) {
    score += 2;
  }
  if (cjk < 0.05 && asciiLetterCount(trimmed) > 40) {
    score += 1;
  }

  return score;
}

function answerScore(paragraph: string): number {
  let score = 0;
  const trimmed = paragraph.trim();
  const cjk = cjkRatio(trimmed);

  if (ANSWER_HINT_PATTERN.test(trimmed)) {
    score += 4;
  }
  if (TABLE_HINT_PATTERN.test(trimmed)) {
    score += 2;
  }
  if (cjk > 0.2 && trimmed.length > 24) {
    score += 2;
  }
  if (/。|！|？/.test(trimmed) && !REASONING_HINT_PATTERN.test(trimmed)) {
    score += 1;
  }
  if (/^(?:language|原句|总结|结论|第一部分|第二部分)/im.test(trimmed)) {
    score += 1;
  }

  return score;
}

function findScoredParagraphBoundary(raw: string): SplitBoundary | null {
  const paragraphs = splitParagraphs(raw);
  if (paragraphs.length < 3) {
    return null;
  }

  const reasonScores = paragraphs.map((p) => reasoningScore(p.text));
  const answerScores = paragraphs.map((p) => answerScore(p.text));

  const prefixReason: number[] = [];
  const prefixAnswer: number[] = [];
  let reasonAcc = 0;
  let answerAcc = 0;
  for (let i = 0; i < paragraphs.length; i += 1) {
    reasonAcc += reasonScores[i];
    answerAcc += answerScores[i];
    prefixReason[i] = reasonAcc;
    prefixAnswer[i] = answerAcc;
  }

  const suffixReason: number[] = new Array(paragraphs.length).fill(0);
  const suffixAnswer: number[] = new Array(paragraphs.length).fill(0);
  reasonAcc = 0;
  answerAcc = 0;
  for (let i = paragraphs.length - 1; i >= 0; i -= 1) {
    reasonAcc += reasonScores[i];
    answerAcc += answerScores[i];
    suffixReason[i] = reasonAcc;
    suffixAnswer[i] = answerAcc;
  }

  let bestIdx = -1;
  let bestScore = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < paragraphs.length - 1; i += 1) {
    const beforeReason = prefixReason[i];
    const beforeAnswer = prefixAnswer[i];
    const afterReason = suffixReason[i + 1];
    const afterAnswer = suffixAnswer[i + 1];
    const candidate = beforeReason + afterAnswer - beforeAnswer * 0.9 - afterReason * 0.6;

    if (candidate > bestScore) {
      bestScore = candidate;
      bestIdx = i;
    }
  }

  if (bestIdx < 0) {
    return null;
  }

  const answerStart = paragraphs[bestIdx + 1].start;
  const answerText = raw.slice(answerStart).trim();
  if (bestScore < 3.2 || answerText.length < 20) {
    return null;
  }

  return { start: answerStart, end: answerStart };
}

function resolveBoundary(raw: string): SplitBoundary | null {
  return (
    findDirectMarkerBoundary(raw) ??
    findStructuredStepBoundary(raw) ??
    findAnswerLeadBoundary(raw) ??
    findHandoffBoundary(raw) ??
    findScoredParagraphBoundary(raw) ??
    findLanguageShiftBoundary(raw)
  );
}

export function parseThinkingContent(content: string): ThinkingParseResult | null {
  const trimmed = content.trim();
  if (!THOUGHT_PREFIX.test(trimmed)) {
    return null;
  }

  const raw = trimmed.replace(THOUGHT_PREFIX, "").trimStart();
  if (!raw) {
    return { reasoning: "", answer: "" };
  }

  const boundary = resolveBoundary(raw);
  if (!boundary) {
    return { reasoning: raw.trim(), answer: "" };
  }

  const reasoning = raw.slice(0, boundary.start).trim();
  const answer = sanitizeAnswer(raw.slice(boundary.end));
  if (!answer) {
    return { reasoning: raw.trim(), answer: "" };
  }
  return { reasoning, answer };
}
