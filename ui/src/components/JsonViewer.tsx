type JsonViewerProps = {
  data: unknown;
};

export function JsonViewer({ data }: JsonViewerProps) {
  if (data === null || data === undefined) {
    return <div className="empty">No data</div>;
  }

  if (typeof data === "object" && Object.keys(data as object).length === 0) {
    return <div className="empty">No data found.</div>;
  }

  return (
    <pre className="json-viewer">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
