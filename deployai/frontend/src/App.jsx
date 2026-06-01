import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Rocket, Github, Terminal, Globe, CheckCircle, XCircle,
  Clock, Loader, ExternalLink, Trash2, RefreshCw, Cpu,
  Package, Server, AlertTriangle, Zap, Copy, Check, Settings, X
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL || ''

const STATUS_CONFIG = {
  queued:     { color: '#94A3B8', icon: Clock,        label: 'Queued',     bg: '#1E293B' },
  cloning:    { color: '#60A5FA', icon: RefreshCw,    label: 'Cloning',    bg: '#1E3A5F' },
  analyzing:  { color: '#A78BFA', icon: Cpu,          label: 'Analyzing',  bg: '#2D1B69' },
  generating: { color: '#F472B6', icon: Zap,          label: 'Generating', bg: '#4A1942' },
  building:   { color: '#FB923C', icon: Package,      label: 'Building',   bg: '#4A2500' },
  deploying:  { color: '#34D399', icon: Server,       label: 'Deploying',  bg: '#064E3B' },
  running:    { color: '#4ADE80', icon: CheckCircle,  label: 'Live',       bg: '#14532D' },
  failed:     { color: '#F87171', icon: XCircle,      label: 'Failed',     bg: '#450A0A' },
}

const LOG_COLORS = {
  info:    '#CBD5E1',
  warning: '#FCD34D',
  error:   '#F87171',
  success: '#4ADE80',
}

const ACTIVE_STATUSES = ['queued','cloning','analyzing','generating','building','deploying']

function useInterval(callback, delay) {
  const saved = useRef(callback)
  useEffect(() => { saved.current = callback }, [callback])
  useEffect(() => {
    if (delay === null) return
    const id = setInterval(() => saved.current(), delay)
    return () => clearInterval(id)
  }, [delay])
}

// ── Small UI components ──────────────────────────────────────────────────────

function Badge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.queued
  const Icon = cfg.icon
  const spinning = ACTIVE_STATUSES.includes(status)
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 10px', borderRadius: 20,
      background: cfg.bg, color: cfg.color,
      fontSize: 11, fontFamily: 'Space Mono, monospace',
      fontWeight: 700, letterSpacing: '0.05em',
      border: `1px solid ${cfg.color}30`,
      whiteSpace: 'nowrap',
    }}>
      <Icon size={11} style={{ animation: spinning ? 'spin 1s linear infinite' : 'none', flexShrink: 0 }} />
      {cfg.label.toUpperCase()}
    </span>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const handle = () => {
    navigator.clipboard.writeText(text).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={handle} title="Copy" style={{
      background: 'none', border: 'none', cursor: 'pointer',
      color: copied ? '#4ADE80' : '#64748B', display: 'flex', alignItems: 'center', padding: 4,
    }}>
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  )
}

function StackBadge({ stack }) {
  if (!stack || !stack.framework) return null
  const colors = {
    nodejs: '#68A063', python: '#3776AB', java: '#ED8B00',
    go: '#00ADD8', rust: '#B7410E', html: '#E34F26', docker: '#2496ED',
  }
  const color = colors[stack.language] || '#64748B'
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '2px 10px', borderRadius: 20,
      background: `${color}20`, color, border: `1px solid ${color}40`,
      fontSize: 11, fontFamily: 'Space Mono', fontWeight: 700,
    }}>
      {stack.framework.toUpperCase()}
      <span style={{ color: '#475569' }}>:{stack.internal_port}</span>
    </span>
  )
}

function StatBox({ label, value }) {
  if (!value && value !== 0) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={{ fontSize: 10, color: '#334155', fontFamily: 'Space Mono', fontWeight: 700, letterSpacing: '0.08em' }}>
        {label}
      </span>
      <span style={{ fontSize: 12, color: '#94A3B8', fontFamily: 'Space Mono' }}>{value}</span>
    </div>
  )
}

function LogTerminal({ logs, status }) {
  const bottomRef = useRef(null)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs?.length])

  const isActive = ACTIVE_STATUSES.includes(status)

  return (
    <div style={{
      background: '#020617', border: '1px solid #1E293B',
      borderRadius: 12, overflow: 'hidden', fontFamily: 'Space Mono, monospace',
    }}>
      {/* Terminal title bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 16px', background: '#0F172A', borderBottom: '1px solid #1E293B',
      }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {['#FF5F57','#FEBC2E','#28C840'].map(c => (
            <div key={c} style={{ width: 10, height: 10, borderRadius: '50%', background: c }} />
          ))}
        </div>
        <span style={{ color: '#475569', fontSize: 11, marginLeft: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
          <Terminal size={11} /> deployment logs
        </span>
        {isActive && (
          <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, color: '#4ADE80', fontSize: 10 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#4ADE80', animation: 'pulse 1s infinite' }} />
            LIVE
          </span>
        )}
        {!isActive && logs?.length > 0 && (
          <span style={{ marginLeft: 'auto', color: '#334155', fontSize: 10 }}>
            {logs.length} lines
          </span>
        )}
      </div>

      {/* Log lines */}
      <div style={{ padding: '14px 16px', maxHeight: 380, overflowY: 'auto', minHeight: 100 }}>
        {(!logs || logs.length === 0) ? (
          <p style={{ color: '#334155', fontSize: 12 }}>
            {isActive ? 'Starting deployment...' : 'No logs available.'}
          </p>
        ) : (
          logs.map((entry, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, marginBottom: 3, fontSize: 12, lineHeight: 1.65 }}>
              <span style={{ color: '#334155', flexShrink: 0, userSelect: 'none', minWidth: 54 }}>
                {entry.timestamp}
              </span>
              <span style={{ color: LOG_COLORS[entry.level] || LOG_COLORS.info, wordBreak: 'break-word' }}>
                {entry.message}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function DeploymentCard({ dep, isSelected, onSelect, onDelete }) {
  const cfg = STATUS_CONFIG[dep.status] || STATUS_CONFIG.queued
  const isLive = dep.status === 'running'
  return (
    <div
      onClick={() => onSelect(dep.id)}
      style={{
        padding: '12px 14px', borderRadius: 10, cursor: 'pointer',
        background: isSelected ? '#0F1E35' : '#080E1A',
        border: `1px solid ${isSelected ? '#1E4080' : '#0F1E2E'}`,
        display: 'flex', alignItems: 'center', gap: 10,
        transition: 'background 0.15s, border-color 0.15s',
      }}
    >
      <div style={{
        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
        background: cfg.color,
        boxShadow: isLive ? `0 0 8px ${cfg.color}` : 'none',
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: '#E2E8F0', fontSize: 13, fontWeight: 600, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
          {dep.project_name}
        </div>
        <div style={{ color: '#475569', fontSize: 10, fontFamily: 'Space Mono', marginTop: 2 }}>
          {dep.created_at ? new Date(dep.created_at).toLocaleTimeString() : ''}
        </div>
      </div>
      <Badge status={dep.status} />
      <button
        onClick={e => { e.stopPropagation(); onDelete(dep.id) }}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#334155', padding: 4, display: 'flex', borderRadius: 4, flexShrink: 0 }}
      >
        <Trash2 size={13} />
      </button>
    </div>
  )
}

// ── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [form, setForm] = useState({ project_name: '', repo_url: '', ai_api_key: '', ai_provider: 'openrouter' })
  const [deployments, setDeployments] = useState([])   // full deployment objects keyed by id
  const [selectedId, setSelectedId] = useState(null)
  const [deploying, setDeploying] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [errors, setErrors] = useState({})
  const [backendOk, setBackendOk] = useState(null)

  const selected = deployments.find(d => d.id === selectedId) || null
  const isActive = selected ? ACTIVE_STATUSES.includes(selected.status) : false

  // ── Health check ───────────────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setBackendOk(d?.status === 'healthy'))
      .catch(() => setBackendOk(false))
  }, [])

  // ── Merge helper: update a single deployment in state ───────────────────
  const mergeDeployment = useCallback((data) => {
    setDeployments(prev => {
      const exists = prev.find(d => d.id === data.id)
      if (exists) return prev.map(d => d.id === data.id ? { ...d, ...data } : d)
      return [data, ...prev]
    })
  }, [])

  // ── Poll full detail for the selected deployment every 2s ──────────────
  // This is the KEY fix: always fetch full detail (not just logs) so
  // container_id, external_port, internal_port, stack all update.
  const fetchSelectedDetail = useCallback(async () => {
    if (!selectedId) return
    try {
      const r = await fetch(`${API_BASE}/api/deployments/${selectedId}`)
      if (r.ok) {
        const data = await r.json()
        mergeDeployment(data)
      }
    } catch {}
  }, [selectedId, mergeDeployment])

  // Poll fast while active, slow when done
  useInterval(fetchSelectedDetail, selectedId ? (isActive ? 1500 : 5000) : null)

  // ── Poll deployments list for sidebar ─────────────────────────────────
  const refreshList = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/deployments`)
      if (r.ok) {
        const list = await r.json()
        // list only has summary fields; merge without overwriting full details
        setDeployments(prev => {
          const listReversed = [...list].reverse()
          return listReversed.map(item => {
            const existing = prev.find(d => d.id === item.id)
            return existing ? { ...existing, status: item.status, public_url: item.public_url } : item
          })
        })
      }
    } catch {}
  }, [])

  useInterval(refreshList, 4000)
  useEffect(() => { refreshList() }, [])

  // ── Select a deployment: fetch full detail immediately ─────────────────
  const handleSelect = useCallback(async (id) => {
    setSelectedId(id)
    try {
      const r = await fetch(`${API_BASE}/api/deployments/${id}`)
      if (r.ok) {
        const data = await r.json()
        mergeDeployment(data)
      }
    } catch {}
  }, [mergeDeployment])

  // ── Deploy ─────────────────────────────────────────────────────────────
  const validate = () => {
    const e = {}
    if (!form.project_name.trim()) e.project_name = 'Required'
    if (!form.repo_url.trim()) e.repo_url = 'Required'
    else if (!form.repo_url.startsWith('http')) e.repo_url = 'Must start with http'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleDeploy = async () => {
    if (!validate()) return
    setDeploying(true)
    try {
      const r = await fetch(`${API_BASE}/api/deploy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (r.ok) {
        const { deployment_id } = await r.json()
        setForm(f => ({ ...f, project_name: '', repo_url: '' }))
        await refreshList()
        handleSelect(deployment_id)
      }
    } catch {
      setErrors({ submit: 'Cannot connect to backend. Is it running?' })
    } finally {
      setDeploying(false)
    }
  }

  // ── Delete ─────────────────────────────────────────────────────────────
  const handleDelete = async (id) => {
    try {
      await fetch(`${API_BASE}/api/deployments/${id}`, { method: 'DELETE' })
      setDeployments(prev => prev.filter(d => d.id !== id))
      if (selectedId === id) setSelectedId(null)
    } catch {}
  }

  // ── Styles ─────────────────────────────────────────────────────────────
  const S = {
    root: {
      minHeight: '100vh', background: '#050A0F',
      fontFamily: 'Syne, sans-serif', color: '#E2E8F0',
      display: 'grid',
      gridTemplateColumns: '320px 1fr',
      gridTemplateRows: '52px 1fr',
    },
    header: {
      gridColumn: '1 / -1', padding: '0 24px', height: 52,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      background: '#080E1A', borderBottom: '1px solid #0F1E2E',
    },
    sidebar: {
      padding: '20px 16px', borderRight: '1px solid #0F1E2E',
      overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 18,
    },
    main: {
      padding: '24px 28px', overflowY: 'auto',
      display: 'flex', flexDirection: 'column', gap: 20,
    },
    sectionLabel: {
      fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
      color: '#334155', fontFamily: 'Space Mono', marginBottom: 10,
    },
    fieldLabel: {
      display: 'block', marginBottom: 5,
      fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
      color: '#64748B', fontFamily: 'Space Mono',
    },
    input: {
      width: '100%', padding: '9px 12px',
      background: '#040810', border: '1px solid #1E293B',
      borderRadius: 8, color: '#E2E8F0',
      fontSize: 13, fontFamily: 'Syne, sans-serif', outline: 'none',
    },
    deployBtn: {
      width: '100%', padding: '11px',
      background: deploying ? '#1E293B' : 'linear-gradient(135deg,#3B82F6,#6366F1)',
      border: 'none', borderRadius: 8, color: '#fff',
      fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: 14,
      cursor: deploying ? 'not-allowed' : 'pointer',
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    },
    card: {
      background: '#080E1A', border: '1px solid #0F1E2E',
      borderRadius: 12, padding: 20,
    },
    errorText: { color: '#F87171', fontSize: 11, marginTop: 4, fontFamily: 'Space Mono' },
  }

  return (
    <div style={S.root}>
      <style>{`
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }
        input:focus,select:focus { border-color:#3B82F6!important; }
        ::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-track{background:transparent} ::-webkit-scrollbar-thumb{background:#1E293B;border-radius:4px}
      `}</style>

      {/* ── Header ── */}
      <header style={S.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width:30, height:30, borderRadius:8, background:'linear-gradient(135deg,#3B82F6,#6366F1)', display:'flex', alignItems:'center', justifyContent:'center' }}>
            <Rocket size={15} color="#fff" />
          </div>
          <span style={{ fontSize:16, fontWeight:800, letterSpacing:'-0.02em' }}>
            Deploy<span style={{ color:'#3B82F6' }}>AI</span>
          </span>
          <span style={{ fontSize:9, padding:'2px 7px', borderRadius:20, background:'#0F1E35', color:'#3B82F6', fontFamily:'Space Mono', border:'1px solid #1E4080' }}>BETA</span>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:14 }}>
          <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, fontFamily:'Space Mono', color: backendOk===null ? '#64748B' : backendOk ? '#4ADE80' : '#F87171' }}>
            <div style={{ width:6, height:6, borderRadius:'50%', background:'currentColor' }} />
            {backendOk===null ? 'Connecting...' : backendOk ? 'Backend Online' : 'Backend Offline'}
          </div>
          <button onClick={() => setShowSettings(v => !v)} style={{ background:'#0F1E2E', border:'1px solid #1E293B', borderRadius:8, color:'#64748B', padding:'5px 10px', cursor:'pointer', display:'flex', alignItems:'center', gap:6, fontSize:12 }}>
            <Settings size={13} /> Settings
          </button>
        </div>
      </header>

      {/* ── Sidebar ── */}
      <aside style={S.sidebar}>
        <div>
          <div style={S.sectionLabel}>NEW DEPLOYMENT</div>
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>

            <div>
              <label style={S.fieldLabel}>PROJECT NAME</label>
              <input style={{ ...S.input, borderColor: errors.project_name ? '#F87171' : '#1E293B' }}
                placeholder="my-awesome-app" value={form.project_name}
                onChange={e => setForm(f => ({ ...f, project_name: e.target.value }))} />
              {errors.project_name && <p style={S.errorText}>{errors.project_name}</p>}
            </div>

            <div>
              <label style={S.fieldLabel}>GITHUB REPO URL</label>
              <div style={{ position:'relative' }}>
                <Github size={13} style={{ position:'absolute', left:10, top:'50%', transform:'translateY(-50%)', color:'#475569' }} />
                <input style={{ ...S.input, paddingLeft:30, borderColor: errors.repo_url ? '#F87171' : '#1E293B' }}
                  placeholder="https://github.com/user/repo" value={form.repo_url}
                  onChange={e => setForm(f => ({ ...f, repo_url: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && handleDeploy()} />
              </div>
              {errors.repo_url && <p style={S.errorText}>{errors.repo_url}</p>}
            </div>

            {showSettings && (
              <div style={{ padding:14, background:'#040810', border:'1px solid #1E293B', borderRadius:10, display:'flex', flexDirection:'column', gap:10, animation:'fadeIn 0.2s ease' }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <span style={{ ...S.fieldLabel, margin:0 }}>AI SETTINGS (OPTIONAL)</span>
                  <button onClick={() => setShowSettings(false)} style={{ background:'none', border:'none', cursor:'pointer', color:'#475569' }}><X size={12}/></button>
                </div>
                <div>
                  <label style={S.fieldLabel}>AI PROVIDER</label>
                  <select value={form.ai_provider} onChange={e => setForm(f => ({ ...f, ai_provider: e.target.value }))}
                    style={{ ...S.input, cursor:'pointer' }}>
                    <option value="groq">Groq (Llama 3.3)</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="openai">OpenAI (GPT-4o mini)</option>
                    <option value="gemini">Google Gemini</option>
                  </select>
                </div>
                <div>
                  <label style={S.fieldLabel}>API KEY</label>
                  <input type="password" style={S.input} placeholder="sk-..."
                    value={form.ai_api_key} onChange={e => setForm(f => ({ ...f, ai_api_key: e.target.value }))} />
                  <p style={{ ...S.errorText, color:'#475569', marginTop:4 }}>Leave blank to use fallback templates</p>
                </div>
              </div>
            )}

            {errors.submit && <p style={S.errorText}>{errors.submit}</p>}

            <button style={S.deployBtn} onClick={handleDeploy} disabled={deploying}>
              {deploying
                ? <><Loader size={14} style={{ animation:'spin 1s linear infinite' }}/> Deploying...</>
                : <><Rocket size={14}/> Analyze &amp; Deploy</>}
            </button>
          </div>
        </div>

        {deployments.length > 0 && (
          <div>
            <div style={S.sectionLabel}>DEPLOYMENTS ({deployments.length})</div>
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              {deployments.map(d => (
                <DeploymentCard key={d.id} dep={d}
                  isSelected={selectedId === d.id}
                  onSelect={handleSelect} onDelete={handleDelete} />
              ))}
            </div>
          </div>
        )}
      </aside>

      {/* ── Main panel ── */}
      <main style={S.main}>
        {!selected ? (
          <div style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:14, opacity:0.4 }}>
            <div style={{ width:72, height:72, borderRadius:18, background:'linear-gradient(135deg,#3B82F620,#6366F120)', border:'1px solid #3B82F630', display:'flex', alignItems:'center', justifyContent:'center' }}>
              <Rocket size={28} color="#3B82F6" />
            </div>
            <div style={{ textAlign:'center' }}>
              <p style={{ fontSize:17, fontWeight:700, color:'#475569' }}>No deployment selected</p>
              <p style={{ fontSize:13, color:'#334155', marginTop:4 }}>Deploy a repo or click one from the list</p>
            </div>
          </div>
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:20, animation:'fadeIn 0.25s ease' }}>

            {/* Title row */}
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:10, flexWrap:'wrap' }}>
                <h1 style={{ fontSize:22, fontWeight:800, letterSpacing:'-0.02em' }}>{selected.project_name}</h1>
                <Badge status={selected.status} />
                {selected.stack && <StackBadge stack={selected.stack} />}
              </div>
              <p style={{ color:'#475569', fontSize:11, fontFamily:'Space Mono', marginTop:5,
                overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:'100%' }}>
                {selected.repo_url}
              </p>
            </div>

            {/* Live URL card */}
            {selected.public_url && (
              <div style={{ ...S.card, borderColor:'#1E4080', background:'#060F1E' }}>
                <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.1em', color:'#3B82F6',
                  fontFamily:'Space Mono', marginBottom:12, display:'flex', alignItems:'center', gap:6 }}>
                  <CheckCircle size={11}/> DEPLOYMENT LIVE
                </div>

                {/* URL bar */}
                <div style={{ display:'flex', alignItems:'center', gap:10, padding:'11px 14px',
                  background:'#0A1628', border:'1px solid #1E4080', borderRadius:10,
                  fontFamily:'Space Mono', fontSize:13, color:'#60A5FA' }}>
                  <Globe size={14} style={{ flexShrink:0 }}/>
                  <span style={{ flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                    {selected.public_url}
                  </span>
                  <CopyButton text={selected.public_url} />
                  <a href={selected.public_url} target="_blank" rel="noopener noreferrer"
                    style={{ color:'#60A5FA', display:'flex', alignItems:'center' }}>
                    <ExternalLink size={14}/>
                  </a>
                </div>

                {/* Stats row — the fields that were missing */}
                <div style={{ display:'flex', gap:24, marginTop:16, flexWrap:'wrap' }}>
                  <StatBox label="CONTAINER ID"   value={selected.container_id} />
                  <StatBox label="EXTERNAL PORT"  value={selected.external_port} />
                  <StatBox label="INTERNAL PORT"  value={selected.internal_port} />
                  <StatBox label="FRAMEWORK"      value={selected.stack?.framework?.toUpperCase()} />
                  <StatBox label="LANGUAGE"       value={selected.stack?.language} />
                </div>
              </div>
            )}

            {/* Error card */}
            {selected.status === 'failed' && selected.error && (
              <div style={{ ...S.card, borderColor:'#450A0A', background:'#0D0202' }}>
                <div style={{ display:'flex', gap:10, alignItems:'flex-start' }}>
                  <AlertTriangle size={16} color="#F87171" style={{ flexShrink:0, marginTop:2 }}/>
                  <div>
                    <p style={{ color:'#F87171', fontWeight:700, marginBottom:6 }}>Deployment Failed</p>
                    <pre style={{ color:'#94A3B8', fontSize:12, fontFamily:'Space Mono', lineHeight:1.6,
                      whiteSpace:'pre-wrap', wordBreak:'break-word', margin:0 }}>
                      {selected.error}
                    </pre>
                  </div>
                </div>
              </div>
            )}

            {/* Logs */}
            <div>
              <div style={S.sectionLabel}>DEPLOYMENT LOGS</div>
              <LogTerminal logs={selected.logs || []} status={selected.status} />
            </div>

            {/* Generated Dockerfile */}
            {selected.dockerfile && (
              <div>
                <div style={{ ...S.sectionLabel, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <span>GENERATED DOCKERFILE</span>
                  <CopyButton text={selected.dockerfile} />
                </div>
                <div style={{ background:'#020617', border:'1px solid #1E293B', borderRadius:10, overflow:'hidden' }}>
                  <pre style={{ padding:16, margin:0, overflowX:'auto', fontSize:11,
                    fontFamily:'Space Mono', color:'#94A3B8', lineHeight:1.7,
                    maxHeight:300, overflowY:'auto' }}>
                    {selected.dockerfile}
                  </pre>
                </div>
              </div>
            )}

          </div>
        )}
      </main>
    </div>
  )
}
