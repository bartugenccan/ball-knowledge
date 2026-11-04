import { SOURCE_HINT } from "@/lib/format";
import type { AttributeMeta } from "@/lib/types";

/** What a rating means and what goes into it. Opens through the `.hint` parent on hover, focus or tap. */
export function AttributeHintCard({ attribute }: { attribute: AttributeMeta }) {
  const { hint, description, source } = attribute;
  return (
    <div id={`hint-${attribute.key}`} role="tooltip" className="hint-card">
      <p className="font-semibold text-ink">{hint?.what ?? description}</p>
      {hint && <p className="mt-1.5">{hint.how}</p>}
      {hint?.note && <p className="mt-1.5 text-dim">{hint.note}</p>}
      {!hint && <p className="mt-1.5 text-dim">{SOURCE_HINT[source]}</p>}
    </div>
  );
}
