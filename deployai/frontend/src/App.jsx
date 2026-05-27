import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Rocket, Github, Terminal, Globe, CheckCircle, XCircle,
  Clock, Loader, ChevronDown, ChevronRight, ExternalLink,
  Trash2, RefreshCw, Cpu, Package, Server, AlertTriangle,
  Zap, Shield, Copy, Check, Settings, X, Plus
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL || ''

const STATUS_CONFIG = {
  queued:     { color: '#94A3B8', icon: Clock,       label: 'Queued',     bg: '#1E293B' },
  cloning:    { color: '#60A5FA', icon: RefreshCw,   label: 'Cloning',    bg: '#1E3A5F' },
  analyzing:  { color: '#A78BFA', icon: Cpu,         label: 'Analyzing',  bg: '#2D1B69' },
  generating: { color: '#F472B6', icon: Zap,         label: 'Generating', bg: '#4A1942' },
  building:   { color: '#FB923C', icon: Package,     label: 'Building',   bg: '#4A2500' },
  deploying:  { color: '#34D399', icon: Server,      label: 'Deploying',  bg: '#064E3B' },
  running:    { color: '#4ADE80', icon: CheckCircle, label: 'Live',       bg: '#14532D' },
  failed:     { color: '#F87171', icon: XCircle,     label: 'Failed',     bg: '#450A0A' },
}

const LOG_COLORS = {
  info:    '#CBD5E1',
  warning: '#FCD34D',
  error:   '#F87171',
  success: '#4ADE80',
}

function useInterval(callback, delay) {
  const savedCallback = useRef(callback)
  useEffect(() => { savedCallback.current = callback }, [callback])
  useEffect(() => {
    if (delay === null) return
    const id = setInterval(() => savedCallback.current(), delay)
    return () => clearInterval(id)
  }, [delay])
}

function Badge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.queued
  const Icon = cfg.icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 10px', borderRadius: 20,
      background: cfg.bg, color: cfg.color,
      fontSize: 11, fontFamily: 'Space Mono, monospace',
      fontWeight: 700, letterSpacing: '0.05em',
      border: `1px solid ${cfg.color}30`,
    }}>
      <Icon size={11} style={{ animation: ['cloning','analyzing','generating','building','deploying'].includes(status) ? 'spin 1s linear infinite' : 'none' }} />
      {cfg.label.toUpperCase()}
    </span>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) }}
      style={{ background: 'none', border: 'none', cursor: 'pointer', color: copied ? '#4ADE80' : '#64748B', display: 'flex', alignItems: 'center' }}>
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  )
}

function LogTerminal({ logs, status }) {
  const bottomRef = useRef(null)
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [logs])

  const isActive = !['running', 'failed'].includes(status)

  return (
    <div style={{
      background: '#020617', border: '1px solid #1E293B',
      borderRadius: 12, overflow: 'hidden', fontFamily: 'Space Mono, monospace',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 16px', background: '#0F172A',
        borderBottom: '1px solid #1E293B',
      }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {['#FF5F57','#FEBC2E','#28C840'].map(c => (
            <div key={c} style={{ width: 10, height: 10, borderRadius: '50%', background: c }} />
          ))}
        </div>
        <span style={{ color: '#475569', fontSize: 11, marginLeft: 8 }}>
          <Terminal size={11} style={{ display: 'inline', marginRight: 5 }} />
          deployment logs
        </span>
        {isActive && (
          <span style={{
            marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4,
            color: '#4ADE80', fontSize: 10,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#4ADE80', animation: 'pulse 1s infinite' }} />
            LIVE
          </span>
        )}
      </div>
      <div style={{ padding: 16, maxHeight: 360, overflowY: 'auto', minHeight: 120 }}>
        {logs.length === 0 ? (
          <p style={{ color: '#334155', fontSize: 12 }}>Waiting for deployment to start...</p>
        ) : (
          logs.map((log, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, marginBottom: 4, fontSize: 12, lineHeight: 1.6 }}>
              <span style={{ color: '#334155', flexShrink: 0, userSelect: 'none' }}>{log.timestamp}</span>
              <span style={{ color: LOG_COLORS[log.level] || LOG_COLORS.info, wordBreak: 'break-word' }}>
                {log.message}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function DeploymentCard({ deployment, onDelete, onSelect, isSelected }) {
  const cfg = STATUS_CONFIG[deployment.status] || STATUS_CONFIG.queued

  return (
    <div onClick={() => onSelect(deployment.id)}
      style={{
        padding: '14px 16px',
        background: isSelected ? '#0F1E35' : '#080E1A',
        border: `1px solid ${isSelected ? '#1E4080' : '#0F1E2E'}`,
        borderRadius: 10, cursor: 'pointer',
        transition: 'all 0.15s ease',
        display: 'flex', alignItems: 'center', gap: 12,
      }}
    >
      <div style={{
        width: 8, height: 8, borderRadius: '50%',
        background: cfg.color, flexShrink: 0,
        boxShadow: deployment.status === 'running' ? `0 0 8px ${cfg.color}` : 'none',
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: '#E2E8F0', fontSize: 13, fontWeight: 600, truncate: true, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
          {deployment.project_name}
        </div>
        <div style={{ color: '#475569', fontSize: 11, fontFamily: 'Space Mono', marginTop: 2 }}>
          {new Date(deployment.created_at).toLocaleTimeString()}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Badge status={deployment.status} />
        <button onClick={e => { e.stopPropagation(); onDelete(deployment.id) }}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#334155', padding: 4, display: 'flex', borderRadius: 4 }}>
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  )
}

function StackBadge({ stack }) {
  if (!stack) return null
  const colors = {
    nodejs: '#68A063', python: '#3776AB', java: '#ED8B00',
    go: '#00ADD8', rust: '#B7410E', html: '#E34F26', docker: '#2496ED'
  }
  const color = colors[stack.language] || '#64748B'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={{
        padding: '2px 10px', borderRadius: 20,
        background: `${color}20`, color: color,
        fontSize: 11, fontFamily: 'Space Mono', fontWeight: 700,
        border: `1px solid ${color}40`,
      }}>
        {stack.framework.toUpperCase()}
      </span>
      <span style={{ color: '#475569', fontSize: 11, fontFamily: 'Space Mono' }}>
        :{stack.internal_port}
      </span>
    </div>
  )
}

export default function App() {
  const [form, setForm] = useState({
    project_name: '',
    repo_url: '',
    ai_api_key: '',
    ai_provider: 'groq',
  })
  const [deployments, setDeployments] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [deploying, setDeploying] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [logOffset, setLogOffset] = useState(0)
  const [errors, setErrors] = useState({})
  const [backendOk, setBackendOk] = useState(null)

  const selected = deployments.find(d => d.id === selectedId)
  const isActive = selected && !['running', 'failed'].includes(selected.status)

  // Health check
  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setBackendOk(d?.status === 'healthy'))
      .catch(() => setBackendOk(false))
  }, [])

  // Poll deployments list
  const refreshList = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/deployments`)
      if (r.ok) {
        const data = await r.json()
        setDeployments(data.reverse())
      }
    } catch {}
  }, [])

  useInterval(refreshList, 3000)
  useEffect(() => { refreshList() }, [])

  // Poll logs for active deployment
  const fetchLogs = useCallback(async () => {
    if (!selectedId || !isActive) return
    try {
      const r = await fetch(`${API_BASE}/api/deployments/${selectedId}/logs?since=${logOffset}`)
      if (r.ok) {
        const data = await r.json()
        if (data.logs.length > 0) {
          setLogOffset(prev => prev + data.logs.length)
          setDeployments(prev => prev.map(d =>
            d.id === selectedId
              ? { ...d, logs: [...(d.logs || []), ...data.logs], status: data.status }
              : d
          ))
        }
      }
    } catch {}
  }, [selectedId, isActive, logOffset])

  useInterval(fetchLogs, isActive ? 1000 : null)

  // Load full deployment when selecting
  const handleSelect = useCallback(async (id) => {
    setSelectedId(id)
    setLogOffset(0)
    try {
      const r = await fetch(`${API_BASE}/api/deployments/${id}`)
      if (r.ok) {
        const data = await r.json()
        setDeployments(prev => prev.map(d => d.id === id ? { ...d, ...data } : d))
        setLogOffset(data.logs?.length || 0)
      }
    } catch {}
  }, [])

  const validate = () => {
    const e = {}
    if (!form.project_name.trim()) e.project_name = 'Required'
    if (!form.repo_url.trim()) e.repo_url = 'Required'
    else if (!form.repo_url.startsWith('http')) e.repo_url = 'Must be a valid URL'
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
        const data = await r.json()
        await refreshList()
        handleSelect(data.deployment_id)
        setForm(f => ({ ...f, project_name: '', repo_url: '' }))
      }
    } catch (e) {
      setErrors({ submit: 'Failed to connect to backend. Is it running?' })
    } finally {
      setDeploying(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await fetch(`${API_BASE}/api/deployments/${id}`, { method: 'DELETE' })
      if (selectedId === id) setSelectedId(null)
      await refreshList()
    } catch {}
  }

  const styles = {
    root: {
      minHeight: '100vh',
      background: '#050A0F',
      fontFamily: 'Syne, sans-serif',
      color: '#E2E8F0',
      display: 'grid',
      gridTemplateColumns: '340px 1fr',
      gridTemplateRows: 'auto 1fr',
    },
    header: {
      gridColumn: '1 / -1',
      padding: '0 32px',
      height: 60,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      background: '#080E1A',
      borderBottom: '1px solid #0F1E2E',
    },
    sidebar: {
      padding: '24px 20px',
      borderRight: '1px solid #0F1E2E',
      overflowY: 'auto',
      display: 'flex', flexDirection: 'column', gap: 20,
    },
    main: {
      padding: 28,
      overflowY: 'auto',
      display: 'flex', flexDirection: 'column', gap: 24,
    },
    label: {
      display: 'block', marginBottom: 6,
      fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
      color: '#64748B', fontFamily: 'Space Mono, monospace',
    },
    input: {
      width: '100%', padding: '10px 14px',
      background: '#080E1A', border: '1px solid #1E293B',
      borderRadius: 8, color: '#E2E8F0',
      fontSize: 13, fontFamily: 'Syne, sans-serif',
      outline: 'none', transition: 'border-color 0.2s',
    },
    deployBtn: {
      width: '100%', padding: '12px',
      background: deploying ? '#1E293B' : 'linear-gradient(135deg, #3B82F6, #6366F1)',
      border: 'none', borderRadius: 8, color: '#fff',
      fontFamily: 'Syne, sans-serif', fontWeight: 700,
      fontSize: 14, cursor: deploying ? 'not-allowed' : 'pointer',
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
      transition: 'all 0.2s',
      boxShadow: deploying ? 'none' : '0 0 20px #3B82F620',
    },
    sectionTitle: {
      fontSize: 11, fontWeight: 700, letterSpacing: '0.12em',
      color: '#334155', fontFamily: 'Space Mono', marginBottom: 10,
    },
    card: {
      background: '#080E1A', border: '1px solid #0F1E2E',
      borderRadius: 12, padding: 20,
    },
    urlDisplay: {
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '12px 16px',
      background: '#0A1628', border: '1px solid #1E4080',
      borderRadius: 10, fontFamily: 'Space Mono', fontSize: 13,
      color: '#60A5FA',
    },
    errorText: { color: '#F87171', fontSize: 11, marginTop: 4, fontFamily: 'Space Mono' },
  }

  return (
    <div style={styles.root}>
      <style>{`
        @keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
        @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:0.4 } }
        @keyframes fadeIn { from { opacity:0; transform:translateY(8px) } to { opacity:1; transform:none } }
        ::-webkit-scrollbar { width: 4px }
        ::-webkit-scrollbar-track { background: transparent }
        ::-webkit-scrollbar-thumb { background: #1E293B; border-radius: 4px }
        input:focus { border-color: #3B82F6 !important; }
        select:focus { outline: none; border-color: #3B82F6 !important; }
      `}</style>

      {/* Header */}
      <header style={styles.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, #3B82F6, #6366F1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Rocket size={16} color="#fff" />
          </div>
          <div>
            <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em' }}>Deploy</span>
            <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em', color: '#3B82F6' }}>AI</span>
          </div>
          <span style={{
            fontSize: 10, padding: '2px 8px', borderRadius: 20,
            background: '#0F1E35', color: '#3B82F6', fontFamily: 'Space Mono',
            border: '1px solid #1E4080',
          }}>BETA</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontFamily: 'Space Mono', color: backendOk === null ? '#64748B' : backendOk ? '#4ADE80' : '#F87171' }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
            {backendOk === null ? 'Connecting...' : backendOk ? 'Backend Online' : 'Backend Offline'}
          </div>
          <button onClick={() => setShowSettings(!showSettings)} style={{ background: '#0F1E2E', border: '1px solid #1E293B', borderRadius: 8, color: '#64748B', padding: '6px 10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
            <Settings size={13} /> Settings
          </button>
        </div>
      </header>

      {/* Sidebar */}
      <aside style={styles.sidebar}>
        {/* Deploy Form */}
        <div>
          <p style={styles.sectionTitle}>NEW DEPLOYMENT</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={styles.label}>PROJECT NAME</label>
              <input
                style={{ ...styles.input, borderColor: errors.project_name ? '#F87171' : '#1E293B' }}
                placeholder="my-awesome-app"
                value={form.project_name}
                onChange={e => setForm(f => ({ ...f, project_name: e.target.value }))}
              />
              {errors.project_name && <p style={styles.errorText}>{errors.project_name}</p>}
            </div>
            <div>
              <label style={styles.label}>GITHUB REPO URL</label>
              <div style={{ position: 'relative' }}>
                <Github size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#475569' }} />
                <input
                  style={{ ...styles.input, paddingLeft: 34, borderColor: errors.repo_url ? '#F87171' : '#1E293B' }}
                  placeholder="https://github.com/user/repo"
                  value={form.repo_url}
                  onChange={e => setForm(f => ({ ...f, repo_url: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && handleDeploy()}
                />
              </div>
              {errors.repo_url && <p style={styles.errorText}>{errors.repo_url}</p>}
            </div>

            {showSettings && (
              <div style={{ padding: 14, background: '#080E1A', border: '1px solid #1E293B', borderRadius: 10, display: 'flex', flexDirection: 'column', gap: 12, animation: 'fadeIn 0.2s ease' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ ...styles.label, margin: 0 }}>AI SETTINGS (OPTIONAL)</span>
                  <button onClick={() => setShowSettings(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#475569' }}><X size={12} /></button>
                </div>
                <div>
                  <label style={styles.label}>AI PROVIDER</label>
                  <select
                    value={form.ai_provider}
                    onChange={e => setForm(f => ({ ...f, ai_provider: e.target.value }))}
                    style={{ ...styles.input, cursor: 'pointer' }}
                  >
                    <option value="groq">Groq (Llama 3.3)</option>
                    <option value="openai">OpenAI (GPT-4o mini)</option>
                    <option value="gemini">Google Gemini</option>
                  </select>
                </div>
                <div>
                  <label style={styles.label}>API KEY</label>
                  <input
                    type="password"
                    style={styles.input}
                    placeholder="sk-..."
                    value={form.ai_api_key}
                    onChange={e => setForm(f => ({ ...f, ai_api_key: e.target.value }))}
                  />
                  <p style={{ ...styles.errorText, color: '#64748B', marginTop: 4 }}>Leave blank to use fallback templates</p>
                </div>
              </div>
            )}

            {errors.submit && <p style={styles.errorText}>{errors.submit}</p>}

            <button style={styles.deployBtn} onClick={handleDeploy} disabled={deploying}>
              {deploying ? (
                <><Loader size={15} style={{ animation: 'spin 1s linear infinite' }} /> Deploying...</>
              ) : (
                <><Rocket size={15} /> Analyze & Deploy</>
              )}
            </button>
          </div>
        </div>

        {/* Deployment List */}
        {deployments.length > 0 && (
          <div>
            <p style={styles.sectionTitle}>DEPLOYMENTS ({deployments.length})</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {deployments.map(d => (
                <DeploymentCard
                  key={d.id}
                  deployment={d}
                  onDelete={handleDelete}
                  onSelect={handleSelect}
                  isSelected={selectedId === d.id}
                />
              ))}
            </div>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <main style={styles.main}>
        {!selected ? (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: 16, opacity: 0.5,
          }}>
            <div style={{
              width: 80, height: 80, borderRadius: 20,
              background: 'linear-gradient(135deg, #3B82F620, #6366F120)',
              border: '1px solid #3B82F630',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Rocket size={32} color="#3B82F6" />
            </div>
            <div style={{ textAlign: 'center' }}>
              <p style={{ fontSize: 18, fontWeight: 700, color: '#475569' }}>No deployment selected</p>
              <p style={{ fontSize: 13, color: '#334155', marginTop: 4 }}>Deploy a repo to get started</p>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20, animation: 'fadeIn 0.3s ease' }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <h1 style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em' }}>
                    {selected.project_name}
                  </h1>
                  <Badge status={selected.status} />
                  {selected.stack && <StackBadge stack={selected.stack} />}
                </div>
                <p style={{ color: '#475569', fontSize: 12, fontFamily: 'Space Mono', marginTop: 6 }}>
                  {selected.repo_url}
                </p>
              </div>
            </div>

            {/* Public URL */}
            {selected.public_url && (
              <div style={{ ...styles.card, borderColor: '#1E4080', background: '#060F1E' }}>
                <p style={{ ...styles.sectionTitle, color: '#3B82F6', marginBottom: 12 }}>
                  <CheckCircle size={11} style={{ display: 'inline', marginRight: 6 }} />
                  DEPLOYMENT LIVE
                </p>
                <div style={styles.urlDisplay}>
                  <Globe size={15} style={{ flexShrink: 0 }} />
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {selected.public_url}
                  </span>
                  <CopyButton text={selected.public_url} />
                  <a href={selected.public_url} target="_blank" rel="noopener noreferrer"
                    style={{ color: '#60A5FA', display: 'flex' }}>
                    <ExternalLink size={14} />
                  </a>
                </div>
                <div style={{ display: 'flex', gap: 16, marginTop: 14, flexWrap: 'wrap' }}>
                  {[
                    { label: 'Container', value: selected.container_id },
                    { label: 'External Port', value: selected.external_port },
                    { label: 'Internal Port', value: selected.internal_port },
                  ].map(({ label, value }) => value && (
                    <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span style={{ fontSize: 10, color: '#334155', fontFamily: 'Space Mono', fontWeight: 700 }}>{label.toUpperCase()}</span>
                      <span style={{ fontSize: 12, color: '#94A3B8', fontFamily: 'Space Mono' }}>{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Error */}
            {selected.status === 'failed' && selected.error && (
              <div style={{ ...styles.card, borderColor: '#450A0A', background: '#0D0202' }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <AlertTriangle size={16} color="#F87171" style={{ flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <p style={{ color: '#F87171', fontWeight: 700, marginBottom: 4 }}>Deployment Failed</p>
                    <p style={{ color: '#94A3B8', fontSize: 13, fontFamily: 'Space Mono', lineHeight: 1.6 }}>{selected.error}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Logs */}
            <div>
              <p style={styles.sectionTitle}>DEPLOYMENT LOGS</p>
              <LogTerminal logs={selected.logs || []} status={selected.status} />
            </div>

            {/* Dockerfile */}
            {selected.dockerfile && (
              <div>
                <p style={styles.sectionTitle}>GENERATED DOCKERFILE</p>
                <div style={{
                  background: '#020617', border: '1px solid #1E293B',
                  borderRadius: 12, overflow: 'hidden',
                }}>
                  <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '8px 16px', background: '#0F172A', borderBottom: '1px solid #1E293B',
                  }}>
                    <span style={{ fontSize: 11, color: '#475569', fontFamily: 'Space Mono' }}>Dockerfile</span>
                    <CopyButton text={selected.dockerfile} />
                  </div>
                  <pre style={{
                    padding: 16, overflowX: 'auto', fontSize: 11,
                    fontFamily: 'Space Mono', color: '#94A3B8',
                    lineHeight: 1.7, maxHeight: 320, overflowY: 'auto',
                    margin: 0,
                  }}>
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
