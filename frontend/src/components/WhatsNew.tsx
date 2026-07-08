import { RELEASE_NOTES } from '../releaseNotes'

export function WhatsNew({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="What's New">
        <div className="modal-head">
          <h2>What’s New</h2>
          <button className="chip" onClick={onClose} type="button">
            Close
          </button>
        </div>
        <div className="modal-body">
          {RELEASE_NOTES.map((r) => (
            <div key={r.version} className="release">
              <h3>
                v{r.version} <span className="dim">· {r.date}</span>
              </h3>
              <ul>
                {r.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
