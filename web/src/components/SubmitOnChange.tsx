"use client";

import type { ReactNode } from "react";

/** GET form that applies a select as soon as it changes. Without JS the submit button still works. */
export function SubmitOnChange({ action, className, children }: { action: string; className?: string; children: ReactNode }) {
  return (
    <form action={action} className={className} onChange={(e) => e.currentTarget.requestSubmit()}>
      {children}
    </form>
  );
}
