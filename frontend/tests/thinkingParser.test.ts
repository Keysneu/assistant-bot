import { describe, expect, it } from "vitest";
import { parseThinkingContent } from "../src/utils/thinkingParser";

describe("parseThinkingContent", () => {
  it("returns null for regular answers", () => {
    expect(parseThinkingContent("这是普通回答，没有thought前缀。")).toBeNull();
  });

  it("splits by direct final marker", () => {
    const input = [
      "thought",
      "1. Analyze request.",
      "2. Build answer plan.",
      "Final output generation.",
      "Here is the final answer: 42.",
    ].join("\n");

    const parsed = parseThinkingContent(input);
    expect(parsed).not.toBeNull();
    expect(parsed?.reasoning).toContain("Analyze request");
    expect(parsed?.answer).toContain("Here is the final answer");
  });

  it("splits by self-check handoff + Chinese final answer", () => {
    const input = [
      "thought",
      "Analyze the Request: user asks for translation.",
      "Execution - Target 1: 10 Mainstream Languages.",
      "Review and Formatting: keep it readable.",
      "(Self-Correction: Ensure tone is concise.) (The final output structure looks good.)",
      "这是一个跨学科的请求，下面给出完整回答。",
      "第一部分：十种主流语言翻译。",
    ].join("\n");

    const parsed = parseThinkingContent(input);
    expect(parsed).not.toBeNull();
    expect(parsed?.reasoning).toContain("Analyze the Request");
    expect(parsed?.answer).toContain("这是一个跨学科的请求");
  });

  it("splits by language shift when english reasoning turns into chinese answer", () => {
    const input = [
      "thought",
      "Here's a thinking process to construct the comprehensive answer:",
      "Analyze the Request: user wants a multi-faceted translation.",
      "Execution - Target 1: mainstream languages.",
      "Review and Formatting: ensure readability.",
      "这是一个宏大的请求，我将按照结构化方式回答。",
      "终极答案的跨语种版本如下：",
    ].join("\n\n");

    const parsed = parseThinkingContent(input);
    expect(parsed).not.toBeNull();
    expect(parsed?.reasoning).toContain("Analyze the Request");
    expect(parsed?.answer).toContain("这是一个宏大的请求");
  });

  it("handles long mixed sample similar to production output", () => {
    const input = [
      "thought",
      "Here's a thinking process to construct the comprehensive answer:",
      "Analyze the Request: The user wants a multi-faceted translation and analysis.",
      "Execution - Target 1: 10 Mainstream Languages (Translation).",
      "Execution - Target 2: 3 Dead Languages (Translation/Representation).",
      "Execution - Target 3: 3 Fictional Languages (Representation).",
      "Review and Formatting: Organize the massive amount of information clearly.",
      "(Self-Correction: Ensure the tone remains helpful and intelligent.) (The final output structure looks good.)",
      "这是一个极其宏大且跨学科的请求，它结合了语言学、文化研究、计算机科学和科幻文学。",
      "由于这是一个知识性请求，我将使用我的知识库进行全面回答，并按照您要求的结构进行呈现。",
      "🌌 终极答案的跨界翻译与分析",
    ].join("\n\n");

    const parsed = parseThinkingContent(input);
    expect(parsed).not.toBeNull();
    expect(parsed?.reasoning).toContain("Analyze the Request");
    expect(parsed?.answer).toContain("这是一个极其宏大且跨学科的请求");
    expect(parsed?.answer).toContain("终极答案的跨界翻译与分析");
  });

  it("keeps content in reasoning when answer is not available yet", () => {
    const input = [
      "thought",
      "1. Analyze the question.",
      "2. Plan the response.",
      "3. Check constraints.",
    ].join("\n");

    const parsed = parseThinkingContent(input);
    expect(parsed).not.toBeNull();
    expect(parsed?.reasoning.length).toBeGreaterThan(20);
    expect(parsed?.answer).toBe("");
  });

  it("splits step-like reasoning and final prose block", () => {
    const input = [
      "thought",
      "1. Parse input.",
      "2. Validate schema.",
      "3. Draft final response.",
      "",
      "Final response starts here with a complete paragraph for users.",
    ].join("\n");

    const parsed = parseThinkingContent(input);
    expect(parsed).not.toBeNull();
    expect(parsed?.reasoning).toContain("1. Parse input.");
    expect(parsed?.answer).toContain("Final response starts here");
  });

  it("splits by scored paragraph boundary when no explicit final marker exists", () => {
    const input = [
      "thought",
      "Analyze the Request: translate a famous sentence into multiple languages.",
      "Target 1: choose mainstream languages.",
      "Target 2: include dead and fictional languages.",
      "Review and Formatting: keep structure readable.",
      "终极答案的多语言版本如下。",
      "| 语言 | 翻译 |",
      "| --- | --- |",
      "| 中文 | 生命、宇宙以及万物的终极答案是 42。 |",
    ].join("\n\n");

    const parsed = parseThinkingContent(input);
    expect(parsed).not.toBeNull();
    expect(parsed?.reasoning).toContain("Target 1");
    expect(parsed?.answer).toContain("终极答案的多语言版本如下");
    expect(parsed?.answer).toContain("| 语言 | 翻译 |");
  });
});
