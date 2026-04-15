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
    label: "交易",
    description: "运行、账户、订单与事件。",
  },
  {
    key: "market",
    label: "市场",
    description: "行情、曲线与数据核验。",
  },
  {
    key: "research",
    label: "研究",
    description: "回测、对比与策略参数。",
  },
];

export function ViewSwitcher({ value, onChange }: ViewSwitcherProps) {
  return (
    <nav
      className="view-switcher"
      aria-label="主视图导航"
    >
      {viewOptions.map((option, index) => (
        <button
          key={option.key}
          type="button"
          className={`view-switcher__button ${value === option.key ? "view-switcher__button--active" : ""}`}
          onClick={() => {
            onChange(option.key);
          }}
        >
          <span className="view-switcher__meta">
            <span className="view-switcher__badge">{`0${index + 1}`}</span>
            <span className="view-switcher__label">{option.label}</span>
          </span>
          <span className="view-switcher__description">{option.description}</span>
        </button>
      ))}
    </nav>
  );
}
