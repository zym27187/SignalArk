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
    label: "运维",
    description: "控制平面、持仓、订单与人工操作。",
  },
  {
    key: "market",
    label: "市场",
    description: "K 线监控与盘中盈亏可视化骨架。",
  },
  {
    key: "research",
    label: "研究",
    description: "与第 8 阶段结果契约对齐的回测结果页。",
  },
];

export function ViewSwitcher({ value, onChange }: ViewSwitcherProps) {
  return (
    <nav
      className="view-switcher"
      aria-label="控制台主视图导航"
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
