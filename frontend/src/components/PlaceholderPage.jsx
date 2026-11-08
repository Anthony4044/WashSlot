export function PlaceholderPage({ title, path, story, owner, note, children }) {
  return (
    <section className="page">
      <p className="kicker">
        {story} · {owner}
      </p>
      <h1>{title}</h1>
      <p className="lede">
        Placeholder for <code>{path}</code>. {note}
      </p>
      {children}
    </section>
  )
}
