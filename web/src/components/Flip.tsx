import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentProps } from "react";

const faces = (label: React.ReactNode) => (
  <>
    <span className="f">{label}</span>
    <span className="b" aria-hidden>{label}</span>
  </>
);

/** Primary and secondary actions are cards: hover turns them over. */
export function FlipLink({ ghost, className = "", children, ...rest }: ComponentProps<typeof Link> & { ghost?: boolean }) {
  return (
    <Link {...rest} className={`flip ${ghost ? "flip-ghost" : ""} ${className}`}>
      {faces(children)}
    </Link>
  );
}

export function FlipButton({ ghost, className = "", children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { ghost?: boolean }) {
  return (
    <button {...rest} className={`flip ${ghost ? "flip-ghost" : ""} ${className}`}>
      {faces(children)}
    </button>
  );
}
