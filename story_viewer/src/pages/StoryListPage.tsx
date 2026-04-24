import { useEffect, useState } from "react";
import { listStories, type Story } from "../api/client";

export function StoryListPage() {
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listStories()
      .then((r) => setStories(r.stories))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="empty">Loading…</div>;

  return (
    <div>
      <h1>Stories</h1>
      {stories.length === 0 ? (
        <div className="empty">
          No stories yet. Run the pipeline to generate one.
        </div>
      ) : (
        stories.map((s) => (
          <div key={s.id} className="card">
            <div className="flex justify-between items-center">
              <span className="card-title">{s.title}</span>
              <span className={`chip ${s.status}`}>{s.status}</span>
            </div>
            <div className="card-meta mt-sm">
              <span className="mono">{s.id}</span>
              <span>·</span>
              <span>{new Date(s.created_at * 1000).toLocaleString()}</span>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
