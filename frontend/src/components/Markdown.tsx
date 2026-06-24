import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";

/**
 * Lightweight markdown renderer built on react-markdown + remark-gfm +
 * rehype-highlight. Replaces the lobe-ui Markdown dependency.
 *
 * highlight.js theme CSS is imported once in main.tsx; here we just style the
 * chat-typography container with semantic tokens (constraint: consume semantic
 * classes, no hard-coded feature colors).
 */
export interface MarkdownProps {
  children: string;
  className?: string;
  /** Render with chat-friendly spacing (tighter, no huge headings). */
  variant?: "default" | "chat";
}

const remarkPlugins = [remarkGfm];
const rehypePlugins = [rehypeHighlight];

export function Markdown({ children, className, variant = "default" }: MarkdownProps) {
  return (
    <div
      className={cn(
        "aithru-markdown text-sm leading-relaxed",
        variant === "chat" && "[&_h1]:text-base [&_h2]:text-base [&_h3]:text-sm [&_p]:my-2 [&_ul]:my-2 [&_ol]:my-2 [&_li]:my-0.5",
        variant === "default" && "[&_h1]:text-xl [&_h2]:text-lg [&_h3]:text-base",
        "[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2",
        "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_code]:font-mono",
        "[&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:p-3 [&_pre]:text-xs",
        "[&_pre_code]:bg-transparent [&_pre code]:p-0",
        "[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground",
        "[&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

/** Compact JSON/code block for tool inputs and results. */
export function CodeBlock({
  children,
  language,
  className,
}: {
  children: string;
  language?: string;
  className?: string;
}) {
  return (
    <pre className={cn("overflow-x-auto rounded-md bg-muted p-3 text-xs", className)}>
      <code className={cn("font-mono", language && `language-${language}`)}>{children}</code>
    </pre>
  );
}
