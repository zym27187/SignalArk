import {
  formatDateTime,
  formatDecimal,
  formatSignedMoney,
  formatSymbolLabel,
  titleCase,
} from "../lib/format";
import type { Position, SymbolNameMap } from "../types/api";

interface PositionsTableProps {
  positions: Position[];
  symbolNames: SymbolNameMap;
  error?: string;
}

export function PositionsTable({ positions, symbolNames, error }: PositionsTableProps) {
  return (
    <div className="table-shell">
      {error ? <p className="section-error">持仓数据异常：{error}</p> : null}

      {positions.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">暂无持仓</p>
          <p className="empty-state__copy">
            模拟成交完成后，这里会展示可卖数量以及实时盈亏信息。
          </p>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>标的</th>
              <th>数量</th>
              <th>可卖</th>
              <th>均价</th>
              <th>标记价</th>
              <th>浮动盈亏</th>
              <th>已实现盈亏</th>
              <th>状态</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((position) => (
              <tr key={position.symbol}>
                <td>{formatSymbolLabel(position.symbol, symbolNames)}</td>
                <td>{formatDecimal(position.qty, 0)}</td>
                <td>{formatDecimal(position.sellable_qty, 0)}</td>
                <td>{formatDecimal(position.avg_entry_price, 2)}</td>
                <td>{formatDecimal(position.mark_price, 2)}</td>
                <td>{formatSignedMoney(position.unrealized_pnl)}</td>
                <td>{formatSignedMoney(position.realized_pnl)}</td>
                <td>{titleCase(position.status)}</td>
                <td>{formatDateTime(position.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
