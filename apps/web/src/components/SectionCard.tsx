import type { ReactNode } from "react";

interface SectionCardProps {
  title: string;
  description: string;
  eyebrow?: string;
  className?: string;
  children: ReactNode;
}

export function SectionCard({
  title,
  description,
  eyebrow,
  className,
  children,
}: SectionCardProps) {
  return (
    <section className={`section-card${className ? ` ${className}` : ""}`}>
      <header className="section-card__header">
        <div>
          {eyebrow ? <p className="section-card__eyebrow">{eyebrow}</p> : null}
          <h2 className="section-card__title">{title}</h2>
        </div>
        <p className="section-card__description">{description}</p>
      </header>
      <div className="section-card__body">{children}</div>
    </section>
  );
}
