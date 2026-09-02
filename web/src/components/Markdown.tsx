// The web formatting boundary. Model text is GitHub-flavored Markdown; raw HTML
// is shown as text, not rendered (no rehype-raw), and unsafe link protocols are
// dropped by react-markdown's default urlTransform — so whatever the model
// sends, the page stays legible and script-free.
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}
