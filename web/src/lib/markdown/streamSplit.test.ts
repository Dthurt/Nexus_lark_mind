import { describe, expect, it } from "vitest";

import { splitSettledMarkdown } from "@/lib/markdown/streamSplit";

describe("splitSettledMarkdown", () => {
  it("keeps a growing single line as tail", () => {
    expect(splitSettledMarkdown("Hello wor")).toEqual({
      settled: "",
      tail: "Hello wor",
    });
  });

  it("settles complete lines", () => {
    expect(splitSettledMarkdown("Hello\nwor")).toEqual({
      settled: "Hello\n",
      tail: "wor",
    });
  });

  it("settles closed paragraphs", () => {
    const { settled, tail } = splitSettledMarkdown("Para one.\n\nPara two still");
    expect(settled).toBe("Para one.\n\n");
    expect(tail).toBe("Para two still");
  });

  it("holds an open fence in the tail", () => {
    const src = "Intro\n\n```js\nconst x = 1\n";
    const { settled, tail } = splitSettledMarkdown(src);
    expect(settled).toBe("Intro\n\n");
    expect(tail.startsWith("```js")).toBe(true);
  });

  it("settles a closed fence", () => {
    const src = "Intro\n\n```js\nconst x = 1\n```\n\nmore";
    const { settled, tail } = splitSettledMarkdown(src);
    expect(settled).toContain("```js");
    expect(settled).toContain("```\n\n");
    expect(tail).toBe("more");
  });
});
