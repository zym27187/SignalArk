import type { ReactNode } from "react";

interface SectionCardProps {
  title: string;
  description: string;
  eyebrow?: string;
  children: ReactNode;
}

export function SectionCard({
  title,
  description,
  eyebrow,
  children,
}: SectionCardProps) {
  return (
    <section className="section-card">
      <header className="section-card__header">
        <div>
          {eyebrow ? <p className="section-card__eyebrow">{eyebrow}</p> : null}
          <h2 className="section-card__title">{title}</h2>
        </div>
        <p className="section-card__description">{description}</p>
      </header>
      {children}
    </section>
  );
}

