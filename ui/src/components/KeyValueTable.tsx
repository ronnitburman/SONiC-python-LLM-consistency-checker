type KeyValueTableProps = {
  data: Record<string, unknown>;
};

export function KeyValueTable({ data }: KeyValueTableProps) {
  const entries = Object.entries(data);

  if (entries.length === 0) {
    return <div className="empty">No data found.</div>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Key</th>
          <th>Value</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([key, value]) => (
          <tr key={key}>
            <td className="mono">{key}</td>
            <td className="mono">{String(value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
