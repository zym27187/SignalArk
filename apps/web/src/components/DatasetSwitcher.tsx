interface DatasetSwitcherOption {
  value: string;
  label?: string;
}

interface DatasetSwitcherProps {
  symbolOptions: DatasetSwitcherOption[];
  timeframeOptions: DatasetSwitcherOption[];
  symbol: string;
  timeframe: string;
  onSymbolChange: (symbol: string) => void;
  onTimeframeChange: (timeframe: string) => void;
}

export function DatasetSwitcher({
  symbolOptions,
  timeframeOptions,
  symbol,
  timeframe,
  onSymbolChange,
  onTimeframeChange,
}: DatasetSwitcherProps) {
  return (
    <div className="dataset-switcher">
      <div className="dataset-switcher__group">
        <span className="dataset-switcher__label">标的</span>
        <div
          className="dataset-switcher__options"
          role="tablist"
          aria-label="标的切换"
        >
          {symbolOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={symbol === option.value}
              className={`dataset-switcher__button ${symbol === option.value ? "dataset-switcher__button--active" : ""}`}
              onClick={() => {
                onSymbolChange(option.value);
              }}
            >
              {option.label ?? option.value}
            </button>
          ))}
        </div>
      </div>

      <div className="dataset-switcher__group">
        <span className="dataset-switcher__label">周期</span>
        <div
          className="dataset-switcher__options"
          role="tablist"
          aria-label="周期切换"
        >
          {timeframeOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={timeframe === option.value}
              className={`dataset-switcher__button ${timeframe === option.value ? "dataset-switcher__button--active" : ""}`}
              onClick={() => {
                onTimeframeChange(option.value);
              }}
            >
              {option.label ?? option.value}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
