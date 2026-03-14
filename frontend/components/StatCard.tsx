type StatCardProps = {
  icon: string;
  title: string;
  subtitle: string;
  footer?: string;
  tone?: "blue" | "amber" | "rose";
};

const toneStyles = {
  blue: "bg-blue-50 border-blue-100",
  amber: "bg-amber-50 border-amber-100",
  rose: "bg-rose-50 border-rose-100",
};

export default function StatCard({
  icon,
  title,
  subtitle,
  footer,
  tone = "blue",
}: StatCardProps) {
  return (
    <div className={`rounded-2xl border p-5 ${toneStyles[tone]}`}>
      <div className="mb-3 text-2xl">{icon}</div>
      <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
      <p className="text-slate-700">{subtitle}</p>
      {footer && <p className="mt-3 text-sm text-slate-500">{footer}</p>}
    </div>
  );
}