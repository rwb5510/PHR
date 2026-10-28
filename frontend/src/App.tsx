import { Routes, Route, Link, useParams, useNavigate, Navigate } from 'react-router-dom'
import { useState, useEffect, useRef, ChangeEvent, FormEvent } from 'react'
import { api, apiJson } from './api'

function Disclaimer() {
  return (
    <footer className="disclaimer">
      This is a personal household record. It is not a medical device, not an emergency service, and not a substitute for your clinicians or the original report. Ranges shown are the ranges that came with the result.
    </footer>
  )
}

function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState('owner')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')
  const [needTotp, setNeedTotp] = useState(false)
  const [error, setError] = useState('')
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    const r = await api('/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, totp_code: totp || null }),
    })
    const data = await r.json().catch(() => ({}))
    if (r.ok) {
      onLoggedIn()
      return
    }
    if (String(data.detail) === 'totp_required') {
      setNeedTotp(true)
      setError('Enter the authenticator code.')
      return
    }
    setError('Could not sign in. Check the username and password in your .env file.')
  }
  return (
    <div className="shell">
      <h1>Household PHR</h1>
      <div className="card">
        <form onSubmit={submit}>
          <label>Username
            <input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label>Password
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" />
          </label>
          {needTotp && (
            <label>Authenticator code
              <input value={totp} onChange={e => setTotp(e.target.value)} autoComplete="one-time-code" />
            </label>
          )}
          {error && <p className="error">{error}</p>}
          <button type="submit">Sign in</button>
        </form>
        <p>There is no signup. The first boot creates the household user from <code>BOOTSTRAP_USERNAME</code> / <code>BOOTSTRAP_PASSWORD</code>.</p>
      </div>
      <Disclaimer />
    </div>
  )
}

function Profiles({ me, onRefresh }: { me: any, onRefresh: () => void }) {
  const [profiles, setProfiles] = useState<any[]>([])
  const [legalName, setLegalName] = useState('')
  const [dob, setDob] = useState('')
  const [sex, setSex] = useState('')
  const [error, setError] = useState('')
  const load = () => apiJson<any[]>('/profiles').then(setProfiles).catch(e => setError(e.message))
  useEffect(() => { load() }, [])
  const create = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    await apiJson('/profiles', {
      method: 'POST',
      body: JSON.stringify({ legal_name: legalName, date_of_birth: dob || null, sex: sex || null }),
    })
    setLegalName('')
    setDob('')
    load()
    onRefresh()
  }
  const activate = async (id: number) => {
    await apiJson(`/session/active-profile/${id}`, { method: 'POST' })
    onRefresh()
  }
  return (
    <div>
      <h1>People in this household</h1>
      {error && <p className="error">{error}</p>}
      <div className="card">
        {profiles.length === 0 && <p>No people yet. Add someone to open a chart.</p>}
        <ul>
          {profiles.map(p => (
            <li key={p.id}>
              <Link className="person-name" to={`/profile/${p.id}/dashboard`} onClick={() => activate(p.id)}>{p.legal_name}</Link>
              {p.date_of_birth ? ` — ${p.date_of_birth}` : ''}
              {me?.active_profile_id === p.id ? ' (open)' : ''}
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h2>Add a person</h2>
        <form onSubmit={create}>
          <label>Legal name<input value={legalName} onChange={e => setLegalName(e.target.value)} required /></label>
          <label>Date of birth<input type="date" value={dob} onChange={e => setDob(e.target.value)} /></label>
          <label>Sex for clinical documents
            <select value={sex} onChange={e => setSex(e.target.value)}>
              <option value="">—</option>
              <option value="female">female</option>
              <option value="male">male</option>
              <option value="other">other</option>
              <option value="unknown">unknown</option>
            </select>
          </label>
          <button type="submit">Create profile</button>
        </form>
      </div>
    </div>
  )
}

function ProfileNav() {
  const { id } = useParams()
  const [inbox, setInbox] = useState(0)
  const [profile, setProfile] = useState<any>(null)
  useEffect(() => {
    apiJson(`${'/profiles/' + id}`).then(setProfile).catch(() => setProfile(null))
    apiJson<{ count: number }>(`/profiles/${id}/inbox-count`).then(d => setInbox(d.count || 0)).catch(() => setInbox(0))
  }, [id])
  return (
    <div>
      <h1 className="person-name">{profile?.legal_name || `Profile ${id}`}</h1>
      <nav className="section-nav">
        <Link to={`/profile/${id}/dashboard`}>Dashboard</Link>
        <Link to={`/profile/${id}/encounters`}>Encounters</Link>
        <Link to={`/profile/${id}/medications`}>Medications</Link>
        <Link to={`/profile/${id}/problems`}>Problems</Link>
        <Link to={`/profile/${id}/allergies`}>Allergies</Link>
        <Link to={`/profile/${id}/labs`}>Lab reports</Link>
        <Link to={`/profile/${id}/trends/Sodium`}>Sodium trend</Link>
        <Link to={`/profile/${id}/imaging`}>Imaging</Link>
        <Link to={`/profile/${id}/documents`}>Documents</Link>
        <Link to={`/profile/${id}/inbox`}>Review inbox {inbox > 0 && <span className="badge">{inbox}</span>}</Link>
        <Link to={`/profile/${id}/emergency`}>Emergency</Link>
        <a href={`/api/profiles/${id}/export-ccd`} target="_blank" rel="noreferrer">Export CCD</a>
      </nav>
    </div>
  )
}

function Dashboard() {
  const { id } = useParams()
  const [d, setD] = useState<any>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    apiJson(`/profiles/${id}/dashboard`).then(setD).catch(e => setError(e.message))
  }, [id])
  if (error) return <div className="error">{error}</div>
  if (!d) return <div>Loading…</div>
  const demo = d.demographics
  return (
    <div>
      <div className="card">
        <p className="person-name">{demo.legal_name} {demo.preferred_name ? `(${demo.preferred_name})` : ''} — DOB {demo.date_of_birth || '—'} — {demo.sex || ''}</p>
      </div>
      <div className="card">
        <h3><Link to={`/profile/${id}/problems`}>Active problems</Link></h3>
        <ul>{d.problems.map((p: any) => <li key={p.id}>{p.display_name}</li>)}</ul>
        {d.problems.length === 0 && <p>None entered yet.</p>}
        <h3><Link to={`/profile/${id}/allergies`}>Allergies</Link></h3>
        <ul>{d.allergies.map((a: any) => <li key={a.id}>{a.substance}</li>)}</ul>
        {d.allergies.length === 0 && <p>None entered yet.</p>}
        <h3><Link to={`/profile/${id}/medications`}>Medications</Link></h3>
        <ul>{d.medications.map((m: any) => <li key={m.id}>{m.name}</li>)}</ul>
        {d.medications.length === 0 && <p>None entered yet.</p>}
        {d.next_appointment && <p>Next appointment: {d.next_appointment.when} — {d.next_appointment.provider || ''} — {d.next_appointment.reason || ''}</p>}
        <h3>Recent encounters</h3>
        <ul>{d.recent_encounters.map((e: any) => <li key={e.id}><Link to={`/encounter/${e.id}`}>{e.type} — {e.start} — {e.reason || ''}</Link></li>)}</ul>
        <h3>Flagged labs (L/H)</h3>
        <ul>{d.flagged_labs.map((c: any, i: number) => <li key={i}><Link to={`/profile/${id}/trends/${c.analyte || 'Sodium'}`}>{c.original_name}: {c.value_text} {c.unit || ''} ({c.flag}) {c.ref_low != null ? `${c.ref_low}–${c.ref_high}` : ''}</Link></li>)}</ul>
        <h3>Recent imaging</h3>
        {Object.entries(d.imaging_by_modality || {}).map(([mod, reports]: any) => (
          <div key={mod}>
            <h4>{mod}</h4>
            <ul>{reports.map((r: any) => <li key={r.id}><Link to={`/profile/${id}/imaging`}>{r.performed_at} — {r.impression?.slice(0, 60) || ''}</Link> {r.dicom_study_id && <a href={`/api/viewer/${r.dicom_study_id}`}>viewer</a>}</li>)}</ul>
          </div>
        ))}
      </div>
    </div>
  )
}

function Emergency() {
  const { id } = useParams()
  const [d, setD] = useState<any>(null)
  useEffect(() => { apiJson(`/profiles/${id}/emergency`).then(setD).catch(() => setD(null)) }, [id])
  return (
    <div className="card">
      <h2>Emergency snapshot</h2>
      <p>How to hand this to a clinician: give them this printout or the C-CDA download, not a login.</p>
      {d && (
        <>
          <p className="person-name">{d.demographics.legal_name} — DOB {d.demographics.date_of_birth || '—'} — {d.demographics.sex || ''} — {d.demographics.blood_type || ''}</p>
          <h3>Allergies</h3>
          <ul>{d.allergies.map((a: any, i: number) => <li key={i}>{a.substance} — {a.reaction || ''} ({a.severity})</li>)}</ul>
          <h3>Problems</h3>
          <ul>{d.problems.map((p: any, i: number) => <li key={i}>{p.display_name}</li>)}</ul>
          <h3>Medications</h3>
          <ul>{d.medications.map((m: any, i: number) => <li key={i}>{m.name} {m.dose || ''} {m.dose_unit || ''} {m.frequency || ''}</li>)}</ul>
        </>
      )}
      <p><a href={`/api/profiles/${id}/export-ccd`}>Download C-CDA</a></p>
      <button className="secondary" onClick={() => window.print()}>Print</button>
    </div>
  )
}

function SimpleList({ path, title, fields, createPath, payload }: { path: string, title: string, fields: { key: string, label: string }[], createPath: string, payload: (form: Record<string, string>) => object }) {
  const { id } = useParams()
  const [rows, setRows] = useState<any[]>([])
  const [form, setForm] = useState<Record<string, string>>({})
  const load = () => apiJson<any[]>(path.replace(':id', id || '')).then(setRows).catch(() => setRows([]))
  useEffect(() => { load() }, [id, path])
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    await apiJson(createPath.replace(':id', id || ''), { method: 'POST', body: JSON.stringify(payload(form)) })
    setForm({})
    load()
  }
  return (
    <div className="card">
      <h2>{title}</h2>
      <ul>
        {rows.map(r => (
          <li key={r.id}>{fields.map(f => r[f.key]).filter(Boolean).join(' — ')} {r.status && r.status !== 'active' ? `(${r.status})` : ''}</li>
        ))}
      </ul>
      {rows.length === 0 && <p>Nothing here yet. Add a row below.</p>}
      <form onSubmit={submit}>
        {fields.map(f => (
          <label key={f.key}>{f.label}
            <input value={form[f.key] || ''} onChange={e => setForm({ ...form, [f.key]: e.target.value })} required={f.key === fields[0].key} />
          </label>
        ))}
        <button type="submit">Add</button>
      </form>
    </div>
  )
}

function Encounters() {
  const { id } = useParams()
  const [encs, setEncs] = useState<any[]>([])
  useEffect(() => {
    apiJson<any[]>(`/profiles/${id}/encounters`).then(setEncs).catch(() => setEncs([]))
  }, [id])
  return (
    <div className="card">
      <h2>Encounters</h2>
      <ul>
        {encs.map(e => (
          <li key={e.id}>
            <Link to={`/encounter/${e.id}`}>{e.type} — {e.start} — {e.reason || ''}</Link>
          </li>
        ))}
      </ul>
      {encs.length === 0 && <p>No encounters yet. Uploading a CCD or entering a lab will create them.</p>}
    </div>
  )
}

function EncounterDetail() {
  const { id } = useParams()
  const [enc, setEnc] = useState<any>(null)
  const [orders, setOrders] = useState<any[]>([])
  const [fulfilling, setFulfilling] = useState<any[]>([])
  useEffect(() => {
    apiJson(`/encounters/${id}`).then(setEnc)
    apiJson<any[]>(`/encounters/${id}/orders`).then(setOrders)
    apiJson<any[]>(`/encounters/${id}/fulfilling-orders`).then(setFulfilling)
  }, [id])
  if (!enc) return <div>Loading…</div>
  return (
    <div className="card">
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
    apiJson<any[]>(`/profiles/${id}/lab-reports`).then(setReports).catch(() => setReports([]))
  }, [id])
  return (
    <div className="card">
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
    apiJson(`/lab-reports/${id}`).then(setReport)
  }, [id])
  if (!report) return <div>Loading…</div>
  return (
    <div className="card">
      <h2>{report.panel_name}</h2>
      <p>Collected: {report.collection_time}</p>
      {report.source_document_id && (
        <p><a href={`/api/documents/${report.source_document_id}/file`} target="_blank" rel="noreferrer">Open source document</a></p>
      )}
      <table>
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
    apiJson(`/profiles/${id}/trends/${analyte}`).then(setData).catch(() => setData({ points: [], analyte }))
  }, [id, analyte])
  if (!data) return <div>Loading…</div>
  const byUnit: Record<string, any[]> = {}
  data.points.forEach((pt: any) => {
    const unit = pt.normalized_unit || pt.original_unit || 'unknown'
    if (!byUnit[unit]) byUnit[unit] = []
    byUnit[unit].push(pt)
  })
  return (
    <div className="card">
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
      {data.points.length === 0 && <p>No matched points. Upload the synthetic CCD and accept the sodium proposal.</p>}
    </div>
  )
}

function ImagingLibrary() {
  const { id } = useParams()
  const [groups, setGroups] = useState<any>({})
  const [studies, setStudies] = useState<any[]>([])
  useEffect(() => {
    apiJson(`/profiles/${id}/imaging-reports`).then(setGroups).catch(() => setGroups({}))
    apiJson<any[]>(`/profiles/${id}/studies`).then(setStudies).catch(() => setStudies([]))
  }, [id])
  return (
    <div className="card">
      <h2>Imaging Library</h2>
      <h3>Studies</h3>
      <ul>
        {studies.map(s => (
          <li key={s.id}>
            {s.modality} — {s.study_date || ''} — {s.description || s.study_instance_uid}
            {' '}<a href={`/api/viewer/${s.study_instance_uid}`} target="_blank" rel="noreferrer">Viewer</a>
          </li>
        ))}
      </ul>
      {Object.entries(groups).map(([mod, reports]: any) => (
        <div key={mod}>
          <h3>{modalityLabel(mod)} ({mod})</h3>
          <ul>
            {reports.map((r: any) => (
              <li key={r.id}>
                {r.performed_at} — {r.body_site || ''} — {r.impression?.slice(0, 80) || ''}
                {r.source_document_id && (
                  <> — <a href={`/api/documents/${r.source_document_id}/file`} target="_blank" rel="noreferrer">source</a></>
                )}
                {r.dicom_study_id && <> — study {r.dicom_study_id}</>}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

const MODALITIES: [string, string][] = [
  ['DX', 'X-ray'], ['CT', 'CT'], ['MR', 'MRI'], ['US', 'Ultrasound'], ['MG', 'Mammography'],
  ['NM', 'Nuclear medicine'], ['PT', 'PET'], ['XA', 'Fluoroscopy / angiography'],
  ['DXA', 'Bone density (DXA)'], ['OT', 'Other'],
]
const modalityLabel = (code?: string) => MODALITIES.find(([c]) => c === code)?.[1] || code || ''

function ImagingFromDocument({ docId, onDone }: { docId: number, onDone: (msg: string) => void }) {
  const [f, setF] = useState<Record<string, string>>({ modality: 'DX' })
  const [err, setErr] = useState('')
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value })
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v.trim() !== ''))
    const r = await api(`/documents/${docId}/create-imaging`, { method: 'POST', body: JSON.stringify(body) })
    if (!r.ok) {
      setErr((await r.json().catch(() => ({}))).detail || 'Could not save the imaging report.')
      return
    }
    onDone('Imaging report saved. It is in the Imaging library.')
  }
  return (
    <form className="imaging-form" onSubmit={submit}>
      <label>Modality <select value={f.modality} onChange={set('modality')}>
        {MODALITIES.map(([c, l]) => <option key={c} value={c}>{l} ({c})</option>)}
      </select></label>
      <label>Body site <input value={f.body_site || ''} onChange={set('body_site')} /></label>
      <label>Laterality <select value={f.laterality || ''} onChange={set('laterality')}>
        <option value="">—</option>
        <option value="left">left</option>
        <option value="right">right</option>
        <option value="bilateral">bilateral</option>
      </select></label>
      <label>Performed <input type="date" value={f.performed_at || ''} onChange={set('performed_at')} /></label>
      <label>Findings <textarea rows={4} value={f.findings || ''} onChange={set('findings')} /></label>
      <label>Impression <textarea rows={3} value={f.impression || ''} onChange={set('impression')} /></label>
      <label>Facility <input value={f.facility || ''} onChange={set('facility')} /></label>
      <label>Reporting provider <input value={f.reporting_provider || ''} onChange={set('reporting_provider')} /></label>
      {err && <p className="error">{err}</p>}
      <button type="submit">Save imaging report</button>
    </form>
  )
}

function Documents() {
  const { id } = useParams()
  const [docs, setDocs] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const [useModel, setUseModel] = useState(false)
  const [settings, setSettings] = useState<any>({ mode: 'off' })
  const [openText, setOpenText] = useState<number | null>(null)
  const [extracted, setExtracted] = useState<Record<number, string>>({})
  const [imagingFor, setImagingFor] = useState<number | null>(null)
  const load = () => apiJson<any[]>(`/profiles/${id}/documents`).then(setDocs).catch(() => setDocs([]))
  useEffect(() => {
    load()
    apiJson('/settings').then(setSettings).catch(() => setSettings({ mode: 'off' }))
  }, [id])
  useEffect(() => {
    const busy = docs.some(d => d.job_status === 'queued' || d.job_status === 'processing')
    if (!busy) return
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [docs, id])
  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    fd.append('use_model', String(useModel && settings.mode !== 'off'))
    const r = await api(`/profiles/${id}/documents`, { method: 'POST', body: fd })
    const j = await r.json()
    if (j.duplicate) setMsg(j.warning)
    else setMsg(`Uploaded. Job ${j.job_id} queued.`)
    load()
  }
  const processNow = async (jobId: number) => {
    await api(`/jobs/${jobId}/process`, { method: 'POST' })
    load()
  }
  const retry = async (jobId: number) => {
    await api(`/jobs/${jobId}/retry`, { method: 'POST' })
    load()
  }
  const showText = async (docId: number) => {
    if (openText === docId) {
      setOpenText(null)
      return
    }
    const t = await apiJson<{ extracted_text?: string }>(`/documents/${docId}/text`)
    setExtracted(prev => ({ ...prev, [docId]: t.extracted_text || '' }))
    setOpenText(docId)
  }
  return (
    <div className="card">
      <h2>Documents</h2>
      <p>Max 50 MB per file. PDF, TIFF, JPG, PNG, TXT, XML, MD. A lab result is a test name, a number, and a lab unit on the same row (Sodium 140 mmol/L). Letterhead, phones, comments, and page footers are ignored. Unknown test names go to the review inbox. Imaging reports (X-ray, CT, MRI, ultrasound…) with Findings or Impression go to the review inbox as imaging candidates.</p>
      <label>
        <input type="checkbox" checked={useModel} disabled={settings.mode === 'off'} onChange={e => setUseModel(e.target.checked)} />
        Use model (default off; disabled when mode is off)
      </label>
      <input type="file" onChange={upload} />
      {msg && <p>{msg}</p>}
      <ul>
        {docs.map(d => (
          <li key={d.id} style={{ marginBottom: 12 }}>
            <a href={`/api/documents/${d.id}/file`} target="_blank" rel="noreferrer">{d.filename}</a>
            {' '}— {d.job_status} {d.ocr_used ? '(OCR)' : ''} {d.error || ''}
            {d.job_status === 'queued' && <button className="secondary" onClick={() => processNow(d.job_id)}>Process now</button>}
            {(d.job_status === 'failed' || d.job_status === 'filed' || d.job_status === 'needs_review') && (
              <button className="secondary" onClick={() => retry(d.job_id)}>
                {d.job_status === 'failed' ? 'Retry' : 'Reprocess'}
              </button>
            )}
            <button className="secondary" onClick={() => showText(d.id)}>Extracted text</button>
            {(d.job_status === 'needs_review' || d.job_status === 'filed') && (
              <button className="secondary" onClick={() => setImagingFor(imagingFor === d.id ? null : d.id)}>
                Create imaging report from this document
              </button>
            )}
            {imagingFor === d.id && (
              <ImagingFromDocument docId={d.id} onDone={m => { setImagingFor(null); setMsg(m) }} />
            )}
            {openText === d.id && (
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, background: '#fff', padding: 12, border: '1px solid var(--line)', maxHeight: 240, overflow: 'auto' }}>
                {extracted[d.id] || '(no text yet)'}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Settings() {
  const [s, setS] = useState<any>({ mode: 'off', base_url: '', model: '', llm_autofile: false })
  const [totp, setTotp] = useState<any>(null)
  const [code, setCode] = useState('')
  useEffect(() => { apiJson('/settings').then(setS) }, [])
  const save = async () => {
    const r = await api('/settings', { method: 'POST', body: JSON.stringify(s) })
    setS(await r.json())
  }
  const startTotp = async () => setTotp(await apiJson('/totp/start', { method: 'POST' }))
  const confirmTotp = async () => {
    await apiJson('/totp/confirm', { method: 'POST', body: JSON.stringify({ code }) })
    setTotp({ ...totp, enabled: true })
  }
  return (
    <div className="card">
      <h2>Model settings</h2>
      <p>Key is LLM_API_KEY env var only. No API key field.</p>
      <label>Mode: <select value={s.mode} onChange={e => setS({ ...s, mode: e.target.value })}>
        <option value="off">off</option>
        <option value="remote">remote</option>
        <option value="local">local</option>
      </select></label>
      <label>Base URL: <input value={s.base_url || ''} onChange={e => setS({ ...s, base_url: e.target.value })} /></label>
      <label>Model: <input value={s.model || ''} onChange={e => setS({ ...s, model: e.target.value })} /></label>
      <label>
        <input type="checkbox" checked={!!s.llm_autofile} onChange={e => setS({ ...s, llm_autofile: e.target.checked })} />
        llm_autofile (unsafe — default off)
      </label>
      <button onClick={save}>Save</button>
      <p>{s.llm_autofile_warning}</p>
      <h2>Authenticator</h2>
      <p>Optional. Login works without it until you confirm a code.</p>
      <button className="secondary" onClick={startTotp}>Enroll TOTP</button>
      {totp?.secret && (
        <div>
          <p>Secret: {totp.secret}</p>
          <p style={{ wordBreak: 'break-all' }}>{totp.otpauth_url}</p>
          <label>Code from the app<input value={code} onChange={e => setCode(e.target.value)} /></label>
          <button onClick={confirmTotp}>Confirm</button>
        </div>
      )}
      {totp?.enabled && <p>TOTP is on. The next login will ask for a code.</p>}
    </div>
  )
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function findQuoteRange(text: string, quote: string): [number, number] | null {
  const needle = quote.trim().replace(/\s+/g, ' ')
  if (!needle || !text) return null
  const direct = text.toLowerCase().indexOf(needle.toLowerCase())
  if (direct >= 0) return [direct, direct + needle.length]
  const parts = needle.split(' ').filter(Boolean).map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  if (!parts.length) return null
  const re = new RegExp(parts.join('\\s+'), 'i')
  const m = re.exec(text)
  if (m) return [m.index, m.index + m[0].length]
  return null
}

function fileKind(mime?: string, filename?: string): 'pdf' | 'image' | 'text' | 'other' {
  const m = (mime || '').split(';')[0].trim().toLowerCase()
  const ext = (filename || '').split('.').pop()?.toLowerCase() || ''
  if (m === 'application/pdf' || ext === 'pdf') return 'pdf'
  if (m.startsWith('image/') || ['jpg', 'jpeg', 'png', 'tif', 'tiff'].includes(ext)) return 'image'
  if (m.startsWith('text/') || m.includes('xml') || ['txt', 'md', 'xml'].includes(ext)) return 'text'
  return 'other'
}

function HighlightedExtract({ text, quote }: { text: string, quote?: string | null }) {
  const preRef = useRef<HTMLPreElement>(null)
  const needle = (quote || '').trim()
  const range = findQuoteRange(text || '', quote || '')
  let html = escapeHtml(text || '')
  if (range) {
    html =
      escapeHtml(text.slice(0, range[0])) +
      '<mark id="inbox-quote-mark">' +
      escapeHtml(text.slice(range[0], range[1])) +
      '</mark>' +
      escapeHtml(text.slice(range[1]))
  }
  useEffect(() => {
    preRef.current?.querySelector('#inbox-quote-mark')?.scrollIntoView({ block: 'center', inline: 'nearest' })
  }, [text, quote])
  return (
    <>
      {needle && !range && (
        <p className="muted">Quote not found in extracted text: {needle}</p>
      )}
      <pre
        ref={preRef}
        className="inbox-extracted"
        dangerouslySetInnerHTML={{ __html: html || '(no extracted text)' }}
      />
    </>
  )
}

function Inbox() {
  const { id } = useParams()
  const [props, setProps] = useState<any[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [docMeta, setDocMeta] = useState<{ filename?: string, mime_type?: string } | null>(null)
  const [extracted, setExtracted] = useState('')
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [fileMissing, setFileMissing] = useState(false)
  const [loadingSource, setLoadingSource] = useState(false)
  const [textOpen, setTextOpen] = useState(true)

  const selected = props.find(p => p.id === selectedId) || null

  const load = async (opts?: { afterId?: number, documentId?: number }) => {
    const rows = await apiJson<any[]>(`/profiles/${id}/proposals`).catch(() => [] as any[])
    setProps(rows)
    setSelectedId(prev => {
      if (opts?.afterId != null) {
        const same = rows.filter(r => r.document_id === opts.documentId)
        if (same.length) return same[0].id
        return rows[0]?.id ?? null
      }
      if (prev && rows.some(r => r.id === prev)) return prev
      return prev
    })
  }

  useEffect(() => { load() }, [id])

  useEffect(() => {
    if (!selected?.document_id) {
      setExtracted('')
      setDocMeta(null)
      setSourceError(null)
      setFileMissing(false)
      setLoadingSource(false)
      return
    }
    const docId = selected.document_id
    let cancelled = false
    setLoadingSource(true)
    setSourceError(null)
    setFileMissing(false)
    ;(async () => {
      const [textRes, fileRes] = await Promise.all([
        api(`/documents/${docId}/text`),
        api(`/documents/${docId}/file`, { method: 'HEAD' }),
      ])
      if (cancelled) return
      if (textRes.status === 404) {
        setExtracted('')
        setDocMeta(null)
        setSourceError('Original file is not on disk.')
      } else if (!textRes.ok) {
        setExtracted('')
        setDocMeta(null)
        setSourceError('Could not load extracted text.')
      } else {
        const body = await textRes.json().catch(() => ({}))
        setExtracted(body.extracted_text || '')
        setDocMeta({ filename: body.filename, mime_type: body.mime_type })
      }
      if (fileRes.status === 404) {
        setFileMissing(true)
        setSourceError('Original file is not on disk.')
      } else if (fileRes.status === 405 || fileRes.status === 501) {
        setFileMissing(false)
      } else if (!fileRes.ok) {
        setFileMissing(true)
      } else {
        setFileMissing(false)
      }
      setLoadingSource(false)
    })()
    return () => { cancelled = true }
  }, [selected?.document_id, id])

  const decide = async (pid: number, action: 'accept' | 'reject') => {
    const current = props.find(p => p.id === pid)
    await api(`/proposals/${pid}/${action}`, { method: 'POST' })
    await load({ afterId: pid, documentId: current?.document_id })
  }

  const kind = fileKind(docMeta?.mime_type, docMeta?.filename)
  const fileUrl = selected?.document_id ? `/api/documents/${selected.document_id}/file` : ''

  return (
    <div className="card inbox-card">
      <h2>Review Inbox</h2>
      <p>These are candidate chart rows. Lab lines here did not auto-file (unknown test name, missing collection date, or a non-numeric value). Imaging reports always wait here for review. Letterhead is not listed.</p>
      {props.length === 0 && <p>No pending proposals.</p>}
      <div className="inbox-layout">
        <ul className="inbox-list">
          {props.map(p => (
            <li key={p.id}>
              <button
                type="button"
                className={'inbox-item' + (p.id === selectedId ? ' selected' : '')}
                onClick={() => setSelectedId(p.id)}
              >
                {p.type === 'lab_line' ? (
                  <span>
                    <strong>{p.payload?.original_name}</strong>
                    {' '}{p.payload?.value_text} {p.payload?.unit_original || ''}
                    {p.payload?.ref_text ? ` (${p.payload.ref_text})` : ''}
                    {p.payload?.panel_name && <span className="muted"> · {p.payload.panel_name}</span>}
                    <span className="muted inbox-quote">{p.quote}</span>
                  </span>
                ) : p.type === 'imaging_report' ? (
                  <span>
                    <strong>Imaging: {modalityLabel(p.payload?.modality)}</strong>
                    {p.payload?.body_site && <> · {p.payload.laterality ? `${p.payload.laterality} ` : ''}{p.payload.body_site}</>}
                    {p.payload?.performed_at && <span className="muted"> · {p.payload.performed_at}</span>}
                    {p.payload?.impression && (
                      <span className="inbox-impression">{p.payload.impression.slice(0, 200)}{p.payload.impression.length > 200 ? '…' : ''}</span>
                    )}
                    <span className="muted inbox-quote">{p.quote}</span>
                  </span>
                ) : (
                  <span>{p.type}: {p.quote || JSON.stringify(p.payload)}</span>
                )}
                {p.payload?.dob_mismatch && <span className="error"> {p.payload.dob_mismatch}</span>}
              </button>
            </li>
          ))}
        </ul>
        <div className="inbox-source">
          {!selected && <p className="muted">Select a candidate to see the original page.</p>}
          {selected && loadingSource && <p className="muted">Loading source…</p>}
          {selected && !loadingSource && (
            <>
              <div className="inbox-source-head">
                <strong>{docMeta?.filename || `Document ${selected.document_id}`}</strong>
                {docMeta?.mime_type && <span className="muted"> {docMeta.mime_type}</span>}
              </div>
              {fileMissing && <p className="muted">Original file is not on disk.</p>}
              {!fileMissing && kind === 'pdf' && (
                <iframe title="Source document" className="inbox-frame" src={fileUrl} />
              )}
              {!fileMissing && kind === 'image' && (
                <img className="inbox-frame" alt={docMeta?.filename || 'Source document'} src={fileUrl} />
              )}
              {!fileMissing && kind === 'text' && !extracted && (
                <iframe title="Source document" className="inbox-frame inbox-frame-text" src={fileUrl} />
              )}
              {(kind === 'pdf' || kind === 'image') && (
                <button type="button" className="secondary inbox-toggle" onClick={() => setTextOpen(o => !o)}>
                  {textOpen ? 'Hide extracted text' : 'Show extracted text'}
                </button>
              )}
              {(kind === 'text' || kind === 'other' || textOpen) && (
                <HighlightedExtract text={extracted} quote={selected.quote} />
              )}
              {sourceError && kind !== 'pdf' && kind !== 'image' && <p className="muted">{sourceError}</p>}
              <div className="inbox-actions">
                <button type="button" onClick={() => decide(selected.id, 'accept')}>Accept</button>
                <button type="button" className="danger" onClick={() => decide(selected.id, 'reject')}>Reject</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function ProfileLayout() {
  return (
    <>
      <ProfileNav />
      <Routes>
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="emergency" element={<Emergency />} />
        <Route path="encounters" element={<Encounters />} />
        <Route path="medications" element={
          <SimpleList
            title="Medications"
            path="/profiles/:id/medications"
            createPath="/profiles/:id/medications"
            fields={[{ key: 'name', label: 'Name' }, { key: 'dose', label: 'Dose' }, { key: 'frequency', label: 'Frequency' }]}
            payload={f => ({ name: f.name, dose: f.dose || null, frequency: f.frequency || null })}
          />
        } />
        <Route path="problems" element={
          <SimpleList
            title="Problems"
            path="/profiles/:id/problems"
            createPath="/profiles/:id/problems"
            fields={[{ key: 'display_name', label: 'Name' }]}
            payload={f => ({ display_name: f.display_name })}
          />
        } />
        <Route path="allergies" element={
          <SimpleList
            title="Allergies"
            path="/profiles/:id/allergies"
            createPath="/profiles/:id/allergies"
            fields={[{ key: 'substance', label: 'Substance' }, { key: 'reaction', label: 'Reaction' }]}
            payload={f => ({ substance: f.substance, reaction: f.reaction || null })}
          />
        } />
        <Route path="labs" element={<LabReports />} />
        <Route path="trends/:analyte" element={<TrendView />} />
        <Route path="imaging" element={<ImagingLibrary />} />
        <Route path="documents" element={<Documents />} />
        <Route path="inbox" element={<Inbox />} />
        <Route index element={<Navigate to="dashboard" replace />} />
      </Routes>
    </>
  )
}

export default function App() {
  const [me, setMe] = useState<any | null | undefined>(undefined)
  const navigate = useNavigate()
  const refresh = () => {
    api('/me').then(async r => {
      if (r.status === 401) setMe(null)
      else setMe(await r.json())
    }).catch(() => setMe(null))
  }
  useEffect(() => { refresh() }, [])
  const logout = async () => {
    await api('/logout', { method: 'POST' })
    setMe(null)
    navigate('/')
  }
  if (me === undefined) return <div className="shell">Loading…</div>
  if (!me) return <Login onLoggedIn={refresh} />
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/">Household PHR</Link>
        <div className="row">
          <span>{me.username}</span>
          <Link to="/settings">Settings</Link>
          <button className="secondary" onClick={logout}>Sign out</button>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Profiles me={me} onRefresh={refresh} />} />
        <Route path="/profile/:id/*" element={<ProfileLayout />} />
        <Route path="/encounter/:id" element={<EncounterDetail />} />
        <Route path="/lab-report/:id" element={<LabReportView />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
      <Disclaimer />
    </div>
  )
}
