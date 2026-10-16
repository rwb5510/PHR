import { Routes, Route, Link, useParams } from 'react-router-dom'
import { useState, useEffect, ChangeEvent } from 'react'

const API = '/api'

function Disclaimer() {
  return (
    <footer style={{ marginTop: 40, padding: 12, borderTop: '1px solid #ccc', fontSize: 12 }}>
      This is a personal household record. It is not a medical device, not an emergency service, and not a substitute for your clinicians or the original report. Ranges shown are the ranges that came with the result.
    </footer>
  )
}

function Profiles() {
  const [profiles, setProfiles] = useState<any[]>([])
  useEffect(() => {
    fetch(API + '/profiles').then(r => r.json()).then(setProfiles)
  }, [])
  return (
    <div>
      <h1>Profiles</h1>
      <ul>
        {profiles.map(p => (
          <li key={p.id}><Link to={`/profile/${p.id}`}>{p.legal_name}</Link></li>
        ))}
      </ul>
    </div>
  )
}

function ProfileHome() {
  const { id } = useParams()
  return (
    <div>
      <h1>Profile {id}</h1>
      <nav>
        <Link to={`/profile/${id}/encounters`}>Encounters</Link> |{' '}
        <Link to={`/profile/${id}/labs`}>Lab Reports</Link> |{' '}
        <Link to={`/profile/${id}/trends/Sodium`}>Sodium Trend</Link> |{' '}
        <Link to={`/profile/${id}/imaging`}>Imaging</Link> |{' '}
        <Link to={`/profile/${id}/documents`}>Documents</Link> |{' '}
        <Link to={`/profile/${id}/inbox`}>Review Inbox</Link>
      </nav>
    </div>
  )
}

function Encounters() {
  const { id } = useParams()
  const [encs, setEncs] = useState<any[]>([])
  useEffect(() => {
    fetch(`${API}/profiles/${id}/encounters`).then(r => r.json()).then(setEncs)
  }, [id])
  return (
    <div>
      <h2>Encounters</h2>
      <ul>
        {encs.map(e => (
          <li key={e.id}>
            <Link to={`/encounter/${e.id}`}>{e.type} — {e.start} — {e.reason || ''}</Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

function EncounterDetail() {
  const { id } = useParams()
  const [enc, setEnc] = useState<any>(null)
  const [orders, setOrders] = useState<any[]>([])
  const [fulfilling, setFulfilling] = useState<any[]>([])
  useEffect(() => {
    fetch(`${API}/encounters/${id}`).then(r => r.json()).then(setEnc)
    fetch(`${API}/encounters/${id}/orders`).then(r => r.json()).then(setOrders)
    fetch(`${API}/encounters/${id}/fulfilling-orders`).then(r => r.json()).then(setFulfilling)
  }, [id])
  if (!enc) return <div>Loading...</div>
  return (
    <div>
      <h2>{enc.type} on {enc.start}</h2>
      <p>Reason: {enc.reason}</p>
      <h3>Orders placed here</h3>
      <ul>
        {orders.map(o => <li key={o.id}>{o.name} ({o.category}) — {o.status}</li>)}
      </ul>
      <h3>Orders this encounter fulfills</h3>
      <ul>
        {fulfilling.map(o => <li key={o.order_id}>{o.name}</li>)}
      </ul>
    </div>
  )
}

function LabReports() {
  const { id } = useParams()
  const [reports, setReports] = useState<any[]>([])
  useEffect(() => {
    fetch(`${API}/profiles/${id}/lab-reports`).then(r => r.json()).then(setReports)
  }, [id])
  return (
    <div>
      <h2>Lab Reports</h2>
      <ul>
        {reports.map(r => (
          <li key={r.id}><Link to={`/lab-report/${r.id}`}>{r.panel_name} — {r.collection_time}</Link></li>
        ))}
      </ul>
    </div>
  )
}

function LabReportView() {
  const { id } = useParams()
  const [report, setReport] = useState<any>(null)
  useEffect(() => {
    fetch(`${API}/lab-reports/${id}`).then(r => r.json()).then(setReport)
  }, [id])
  if (!report) return <div>Loading...</div>
  return (
    <div>
      <h2>{report.panel_name}</h2>
      <p>Collected: {report.collection_time}</p>
      {report.source_document_id && (
        <p><a href={`${API}/documents/${report.source_document_id}/file`} target="_blank" rel="noreferrer">Open source document</a></p>
      )}
      <table border={1} cellPadding={6}>
        <thead>
          <tr><th>Name</th><th>Value</th><th>Unit</th><th>Range</th><th>Flag</th></tr>
        </thead>
        <tbody>
          {report.components.map((c: any) => (
            <tr key={c.id}>
              <td>{c.original_name}</td>
              <td>{c.value_text}</td>
              <td>{c.unit_original || ''}</td>
              <td>{c.ref_text || (c.ref_low != null && c.ref_high != null ? `${c.ref_low}–${c.ref_high}` : '')}</td>
              <td>{c.abnormal_flag}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TrendView() {
  const { id, analyte } = useParams()
  const [data, setData] = useState<any>(null)
  useEffect(() => {
    fetch(`${API}/profiles/${id}/trends/${analyte}`).then(r => r.json()).then(setData)
  }, [id, analyte])
  if (!data) return <div>Loading...</div>
  // Group by unit for display; do not force mixed units
  const byUnit: Record<string, any[]> = {}
  data.points.forEach((pt: any) => {
    const unit = pt.normalized_unit || pt.original_unit || 'unknown'
    if (!byUnit[unit]) byUnit[unit] = []
    byUnit[unit].push(pt)
  })
  return (
    <div>
      <h2>{data.analyte} Trend</h2>
      {Object.entries(byUnit).map(([unit, pts]) => (
        <div key={unit}>
          <h3>{unit} series ({pts.length} points)</h3>
          <ul>
            {pts.map((pt: any, i: number) => (
              <li key={i} title={`Original: ${pt.original_value} ${pt.original_unit || ''} | Range: ${pt.ref_low ?? ''}-${pt.ref_high ?? ''} ${pt.ref_text || ''}`}>
                {pt.collected_at}: {pt.normalized_value ?? pt.original_value} {unit}
                {pt.value_numeric == null ? ' (non-numeric)' : ''}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {data.points.length === 0 && <p>No matched points.</p>}
    </div>
  )
}

function ImagingLibrary() {
  const { id } = useParams()
  const [groups, setGroups] = useState<any>({})
  useEffect(() => {
    fetch(`${API}/profiles/${id}/imaging-reports`).then(r => r.json()).then(setGroups)
  }, [id])
  return (
    <div>
      <h2>Imaging Library</h2>
      {Object.entries(groups).map(([mod, reports]: any) => (
        <div key={mod}>
          <h3>{mod}</h3>
          <ul>
            {reports.map((r: any) => (
              <li key={r.id}>
                {r.performed_at} — {r.body_site || ''} — {r.impression?.slice(0, 80) || ''}
                {r.source_document_id && (
                  <> — <a href={`${API}/documents/${r.source_document_id}/file`} target="_blank" rel="noreferrer">source</a></>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

function Documents() {
  const { id } = useParams()
  const [docs, setDocs] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const load = () => fetch(`${API}/profiles/${id}/documents`).then(r => r.json()).then(setDocs)
  useEffect(() => { load() }, [id])
  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    const r = await fetch(`${API}/profiles/${id}/documents`, { method: 'POST', body: fd })
    const j = await r.json()
    if (j.duplicate) setMsg(j.warning)
    else setMsg(`Uploaded. Job ${j.job_id} queued.`)
    load()
  }
  const processNow = async (jobId: number) => {
    await fetch(`${API}/jobs/${jobId}/process`, { method: 'POST' })
    load()
  }
  const retry = async (jobId: number) => {
    await fetch(`${API}/jobs/${jobId}/retry`, { method: 'POST' })
    load()
  }
  return (
    <div>
      <h2>Documents</h2>
      <p>Max 50 MB per file. PDF, TIFF, JPG, PNG, TXT, MD.</p>
      <input type="file" onChange={upload} />
      {msg && <p style={{ color: 'orange' }}>{msg}</p>}
      <ul>
        {docs.map(d => (
          <li key={d.id}>
            <a href={`${API}/documents/${d.id}/file`} target="_blank" rel="noreferrer">{d.filename}</a>
            {' '}— {d.job_status} {d.ocr_used ? '(OCR)' : ''} {d.error || ''}
            {d.job_status === 'queued' && <button onClick={() => processNow(d.job_id)}>Process now</button>}
            {d.job_status === 'failed' && <button onClick={() => retry(d.job_id)}>Retry</button>}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Inbox() {
  const { id } = useParams()
  const [props, setProps] = useState<any[]>([])
  const load = () => fetch(`${API}/profiles/${id}/proposals`).then(r => r.json()).then(setProps)
  useEffect(() => { load() }, [id])
  const accept = async (pid: number) => {
    await fetch(`${API}/proposals/${pid}/accept`, { method: 'POST' })
    load()
  }
  const reject = async (pid: number) => {
    await fetch(`${API}/proposals/${pid}/reject`, { method: 'POST' })
    load()
  }
  return (
    <div>
      <h2>Review Inbox</h2>
      {props.length === 0 && <p>No pending proposals.</p>}
      <ul>
        {props.map(p => (
          <li key={p.id}>
            {p.type}: {p.quote || JSON.stringify(p.payload)}
            <button onClick={() => accept(p.id)}>Accept</button>
            <button onClick={() => reject(p.id)}>Reject</button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function App() {
  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: 900, margin: '0 auto', padding: 16 }}>
      <header>
        <Link to="/">Household PHR</Link>
      </header>
      <Routes>
        <Route path="/" element={<Profiles />} />
        <Route path="/profile/:id" element={<ProfileHome />} />
        <Route path="/profile/:id/encounters" element={<Encounters />} />
        <Route path="/encounter/:id" element={<EncounterDetail />} />
        <Route path="/profile/:id/labs" element={<LabReports />} />
        <Route path="/lab-report/:id" element={<LabReportView />} />
        <Route path="/profile/:id/trends/:analyte" element={<TrendView />} />
        <Route path="/profile/:id/imaging" element={<ImagingLibrary />} />
        <Route path="/profile/:id/documents" element={<Documents />} />
        <Route path="/profile/:id/inbox" element={<Inbox />} />
      </Routes>
      <Disclaimer />
    </div>
  )
}
