import { formatDateTime, formatDecimal, titleCase } from "../lib/format";
import type { FillHistoryEntry } from "../types/api";

interface FillHistoryTableProps {
  fills: FillHistoryEntry[];
  error?: string;
}

export function FillHistoryTable({ fills, error }: FillHistoryTableProps) {
  return (
    <div className="table-shell">
      {error ? <p className="section-error">历史成交异常：{error}</p> : null}

      {fills.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">暂无历史成交</p>
          <p className="empty-state__copy">
            这里会展示已持久化的成交记录，方便复核真实执行结果。
          </p>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>标的</th>
              <th>方向</th>
              <th>数量</th>
              <th>成交价</th>
              <th>费用</th>
              <th>流动性</th>
              <th>只减仓</th>
              <th>成交时间</th>
            </tr>
          </thead>
          <tbody>
            {fills.map((fill) => (
              <tr key={fill.fill_id}>
                <td>{fill.symbol}</td>
                <td>{titleCase(fill.side)}</td>
                <td>{formatDecimal(fill.qty, 0)}</td>
                <td>{formatDecimal(fill.price, 2)}</td>
                <td>{formatDecimal(fill.fee, 2)}</td>
                <td>{titleCase(fill.liquidity_type)}</td>
                <td>{fill.reduce_only ? "是" : "否"}</td>
                <td>{formatDateTime(fill.fill_time)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
