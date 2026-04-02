interface DefinitionGridItem {
  label: string;
  value: string;
  hint?: string;
}

interface DefinitionGridProps {
  items: DefinitionGridItem[];
}

export function DefinitionGrid({ items }: DefinitionGridProps) {
  return (
    <div className="definition-grid">
      {items.map((item) => (
        <article
          key={`${item.label}-${item.value}`}
          className="definition-grid__item"
        >
          <p className="mini-label">{item.label}</p>
          <strong>{item.value}</strong>
          {item.hint ? <p>{item.hint}</p> : null}
        </article>
      ))}
    </div>
  );
}

