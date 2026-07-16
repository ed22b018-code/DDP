// A simple reusable "card" container so every panel looks consistent:
// dark surface, hairline border, rounded corners, a title, and a body.
export default function Card({ title, subtitle, right, children, className = "" }) {
  return (
    <section
      className={`bg-surface border border-hairline rounded-xl p-4 ${className}`}
    >
      {(title || right) && (
        <header className="flex items-start justify-between mb-3">
          <div>
            {title && (
              <h2 className="text-sm font-semibold text-ink tracking-wide">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-xs text-muted mt-0.5">{subtitle}</p>
            )}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}
