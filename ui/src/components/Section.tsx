type SectionProps = {
  title: string;
  children: React.ReactNode;
};

export function Section({ title, children }: SectionProps) {
  return (
    <div className="section">
      <h3>{title}</h3>
      {children}
    </div>
  );
}
