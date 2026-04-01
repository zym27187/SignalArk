import { formatDateTime, formatDecimal, formatSignedMoney, titleCase } from "../lib/format";
import type { Position } from "../types/api";

interface PositionsTableProps {
  positions: Position[];
  error?: string;
}

export function PositionsTable({ positions, error }: PositionsTableProps) {
  return (
    <div className="table-shell">
      {error ? <p className="section-error">Positions feed issue: {error}</p> : null}

      {positions.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">No open positions</p>
          <p className="empty-state__copy">
            Once paper fills settle, open positions will appear here with sellable quantity and PnL.
          </p>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Sellable</th>
              <th>Avg</th>
              <th>Mark</th>
              <th>Unrealized</th>
              <th>Realized</th>
              <th>Status</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((position) => (
              <tr key={position.symbol}>
                <td>{position.symbol}</td>
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

