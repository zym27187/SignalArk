import type { AppView } from "../types/research";

interface ViewSwitcherProps {
  value: AppView;
  onChange: (view: AppView) => void;
}

const viewOptions: Array<{
  key: AppView;
  label: string;
  description: string;
}> = [
  {
    key: "operations",
    label: "Operations",
    description: "Control plane, positions, orders, and operator actions.",
  },
  {
    key: "market",
    label: "Market",
    description: "K-line monitoring and intraday PnL visualization skeleton.",
  },
  {
    key: "research",
    label: "Research",
    description: "Backtest results page aligned to the Phase 8 result contract.",
  },
];

export function ViewSwitcher({ value, onChange }: ViewSwitcherProps) {
  return (
    <nav
      className="view-switcher"
      aria-label="Primary web console view"
    >
      {viewOptions.map((option) => (
        <button
          key={option.key}
          type="button"
          className={`view-switcher__button ${value === option.key ? "view-switcher__button--active" : ""}`}
          onClick={() => {
            onChange(option.key);
          }}
        >
          <span className="view-switcher__label">{option.label}</span>
          <span className="view-switcher__description">{option.description}</span>
        </button>
      ))}
    </nav>
  );
}

