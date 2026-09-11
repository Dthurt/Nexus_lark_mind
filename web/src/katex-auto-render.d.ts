declare module "katex/contrib/auto-render" {
  type Delimiter = { left: string; right: string; display?: boolean };
  type Options = {
    delimiters?: Delimiter[];
    throwOnError?: boolean;
    errorColor?: string;
    macros?: Record<string, string>;
    ignoredTags?: string[];
  };
  export default function renderMathInElement(
    element: HTMLElement,
    options?: Options,
  ): void;
  export function renderMathInElement(
    element: HTMLElement,
    options?: Options,
  ): void;
}
