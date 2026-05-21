import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import {
  Heart, Shield, ClipboardList, Activity, Send, Loader2,
  CheckCircle, XCircle, AlertTriangle, BadgeCheck,
  AlertCircle, ChevronDown, ChevronUp, User,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface GuardrailResult {
  is_health_related: boolean
  no_phi: boolean
  needs_escalation: boolean
}

interface ParserResult {
  intent: string
  chief_complaint: string
  acuity: 'Low' | 'Medium' | 'High'
  summary_response: string
}

interface SafetyResult {
  compliance_pass: boolean
  violations: string[]
}

interface TriageResult {
  guardrail: GuardrailResult | null
  parser: ParserResult | null
  safety: SafetyResult | null
  final_response: string
  pipeline_blocked: boolean
  block_reason: string
  escalation_triggered: boolean
  error: string | null
}

interface ChatMessage {
  id: string
  type: 'user' | 'assistant'
  text: string
  result?: TriageResult
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SAMPLES = [
  "I've had a throbbing headache on the right side for 3 days, worse with light.",
  "I need to refill my lisinopril prescription for blood pressure.",
  "I'd like to schedule an appointment with a dermatologist.",
  "Severe chest pain spreading to my left arm and jaw. Very dizzy. 🚨",
]

const ACUITY_STYLES = {
  Low:    { badge: 'bg-emerald-100 text-emerald-700 border-emerald-200', dot: 'bg-emerald-500', label: 'Low Risk' },
  Medium: { badge: 'bg-amber-100 text-amber-700 border-amber-200',       dot: 'bg-amber-500',   label: 'Medium Risk' },
  High:   { badge: 'bg-red-100 text-red-700 border-red-200',             dot: 'bg-red-500',     label: 'High Risk' },
}

const INTENT_STYLES: Record<string, string> = {
  'Symptom check':       'bg-blue-100 text-blue-700 border-blue-200',
  'Prescription refill': 'bg-violet-100 text-violet-700 border-violet-200',
  'Appointment booking': 'bg-teal-100 text-teal-700 border-teal-200',
}

// ── Typing indicator ─────────────────────────────────────────────────────────

const TypingIndicator = () => (
  <div className="flex items-end gap-2.5 mb-5">
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center flex-shrink-0 shadow-sm mb-0.5">
      <Heart className="w-4 h-4 text-white fill-white" />
    </div>
    <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3.5 shadow-sm">
      <div className="flex gap-1.5 items-center h-4">
        <span className="typing-dot w-2 h-2 bg-gray-400 rounded-full" />
        <span className="typing-dot w-2 h-2 bg-gray-400 rounded-full" />
        <span className="typing-dot w-2 h-2 bg-gray-400 rounded-full" />
      </div>
    </div>
  </div>
)

// ── Expandable pipeline details ───────────────────────────────────────────────

function PipelineDetails({ result }: { result: TriageResult }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-3 pt-3 border-t border-gray-100">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-blue-600 transition-colors"
      >
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        {open ? 'Hide' : 'View'} pipeline details
      </button>
      {open && (
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
          {/* Agent 1 */}
          <div className="rounded-xl overflow-hidden border border-gray-200">
            <div className="px-3 py-2 bg-gradient-to-r from-blue-600 to-blue-500 flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-white" />
              <span className="text-xs font-semibold text-white">Guardrail</span>
            </div>
            <div className="px-3 py-2 text-xs">
              {result.guardrail ? (
                [
                  { label: 'Health Related',   val: result.guardrail.is_health_related, inv: false },
                  { label: 'No PHI',           val: result.guardrail.no_phi,            inv: false },
                  { label: 'Needs Escalation', val: result.guardrail.needs_escalation,  inv: true  },
                ].map(({ label, val, inv }) => {
                  const ok = inv ? !val : val
                  return (
                    <div key={label} className="flex items-center justify-between py-1.5 border-b border-gray-100 last:border-0">
                      <span className="text-gray-500">{label}</span>
                      {ok
                        ? <span className="flex items-center gap-1 text-emerald-600"><CheckCircle className="w-3 h-3" />{String(val)}</span>
                        : <span className="flex items-center gap-1 text-red-500"><XCircle className="w-3 h-3" />{String(val)}</span>}
                    </div>
                  )
                })
              ) : <p className="text-gray-400 italic py-1">Not evaluated</p>}
              {result.block_reason === 'phi_detected' && (
                <p className="mt-1.5 text-red-500 bg-red-50 rounded px-2 py-1">PHI detected — stopped.</p>
              )}
              {result.block_reason === 'not_health_related' && (
                <p className="mt-1.5 text-gray-500 bg-gray-50 rounded px-2 py-1">Not health-related.</p>
              )}
              {result.block_reason === 'guardrail_error' && (
                <p className="mt-1.5 text-orange-600 bg-orange-50 rounded px-2 py-1 break-all">
                  ⚠ Agent error: {result.error ?? 'unknown'}
                </p>
              )}
            </div>
          </div>
          {/* Agent 2 */}
          <div className="rounded-xl overflow-hidden border border-gray-200">
            <div className="px-3 py-2 bg-gradient-to-r from-violet-600 to-violet-500 flex items-center gap-1.5">
              <ClipboardList className="w-3.5 h-3.5 text-white" />
              <span className="text-xs font-semibold text-white">Parser</span>
            </div>
            <div className="px-3 py-2 space-y-2">
              {result.parser ? (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${INTENT_STYLES[result.parser.intent] ?? 'bg-gray-100 text-gray-600 border-gray-200'}`}>
                      {result.parser.intent}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium flex items-center gap-1 ${ACUITY_STYLES[result.parser.acuity]?.badge ?? ''}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${ACUITY_STYLES[result.parser.acuity]?.dot}`} />
                      {result.parser.acuity}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 leading-relaxed">{result.parser.chief_complaint}</p>
                </>
              ) : <p className="text-xs text-gray-400 italic py-1">Not evaluated</p>}
            </div>
          </div>
          {/* Agent 3 */}
          <div className="rounded-xl overflow-hidden border border-gray-200">
            <div className={`px-3 py-2 flex items-center gap-1.5 ${result.safety?.compliance_pass === false ? 'bg-gradient-to-r from-red-600 to-red-500' : 'bg-gradient-to-r from-emerald-600 to-emerald-500'}`}>
              <Activity className="w-3.5 h-3.5 text-white" />
              <span className="text-xs font-semibold text-white">Safety</span>
            </div>
            <div className="px-3 py-2">
              {result.safety ? (
                <>
                  <div className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg mb-2 ${result.safety.compliance_pass ? 'bg-emerald-50' : 'bg-red-50'}`}>
                    {result.safety.compliance_pass
                      ? <><BadgeCheck className="w-3.5 h-3.5 text-emerald-600" /><span className="text-xs font-semibold text-emerald-700">Pass</span></>
                      : <><XCircle className="w-3.5 h-3.5 text-red-500" /><span className="text-xs font-semibold text-red-600">Fail</span></>}
                  </div>
                  {result.safety.violations.length > 0
                    ? result.safety.violations.map(v => (
                        <div key={v} className="text-xs font-mono text-red-600 bg-red-50 px-2 py-1 rounded mb-1">{v}</div>
                      ))
                    : <p className="text-xs text-gray-400">No violations</p>}
                </>
              ) : <p className="text-xs text-gray-400 italic py-1">Not evaluated</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Message bubbles ───────────────────────────────────────────────────────────

function AssistantBubble({ msg }: { msg: ChatMessage }) {
  const r = msg.result
  return (
    <div className="flex items-end gap-2.5 mb-5 msg-enter">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center flex-shrink-0 shadow-sm mb-0.5">
        <Heart className="w-4 h-4 text-white fill-white" />
      </div>
      <div className={`max-w-[82%] bg-white rounded-2xl rounded-bl-sm shadow-sm border overflow-hidden ${
        r?.escalation_triggered ? 'border-red-300' :
        r?.pipeline_blocked     ? 'border-amber-200' : 'border-gray-200'
      }`}>
        {r?.escalation_triggered && (
          <div className="flex items-center gap-2 px-3 py-2 bg-red-600 text-white">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
            <span className="text-xs font-bold uppercase tracking-wide">Emergency Escalation</span>
          </div>
        )}
        <div className="px-4 py-3">
          <p className="text-sm text-gray-800 leading-relaxed">{msg.text}</p>
          {r && <PipelineDetails result={r} />}
        </div>
      </div>
    </div>
  )
}

function UserBubble({ msg }: { msg: ChatMessage }) {
  return (
    <div className="flex items-end justify-end gap-2.5 mb-5 msg-enter">
      <div className="max-w-[78%] bg-gradient-to-br from-blue-600 to-indigo-600 text-white rounded-2xl rounded-br-sm px-4 py-3 shadow-sm">
        <p className="text-sm leading-relaxed">{msg.text}</p>
      </div>
      <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center flex-shrink-0 mb-0.5">
        <User className="w-4 h-4 text-slate-500" />
      </div>
    </div>
  )
}

// ── Welcome screen ────────────────────────────────────────────────────────────

function WelcomeScreen() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-4 py-12">
      <div className="w-16 h-16 mb-5 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-200">
        <Heart className="w-8 h-8 text-white fill-white" />
      </div>
      <h2 className="text-xl font-bold text-gray-800 mb-2">How can I help you today?</h2>
      <p className="text-sm text-gray-400 max-w-sm leading-relaxed">
        Describe your symptoms, request a prescription refill, or book an appointment.
        Our AI system will triage your message safely.
      </p>
      <div className="mt-5 flex flex-wrap gap-2 justify-center">
        <span className="text-xs px-3 py-1 bg-blue-50 text-blue-600 rounded-full border border-blue-100">Symptom Check</span>
        <span className="text-xs px-3 py-1 bg-violet-50 text-violet-600 rounded-full border border-violet-100">Prescription Refill</span>
        <span className="text-xs px-3 py-1 bg-teal-50 text-teal-600 rounded-full border border-teal-100">Appointment Booking</span>
        <span className="text-xs px-3 py-1 bg-red-50 text-red-600 rounded-full border border-red-100">Emergency Escalation</span>
      </div>
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)
  const bottomRef   = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 144) + 'px'
  }, [input])

  const handleSubmit = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return
    setMessages(prev => [...prev, { id: `u${Date.now()}`, type: 'user', text }])
    setInput('')
    setLoading(true)
    setApiError(null)
    try {
      const res = await fetch('https://healthtriage.onrender.com/triage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`)
      }
      const result: TriageResult = await res.json()
      setMessages(prev => [...prev, {
        id: `a${Date.now()}`,
        type: 'assistant',
        text: result.final_response,
        result,
      }])
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Failed to reach the triage API.')
    } finally {
      setLoading(false)
    }
  }, [input, loading])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }

  const isEmpty = messages.length === 0 && !loading

  return (
    <div className="flex flex-col h-screen bg-slate-50">

      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md border-b border-gray-200 flex-shrink-0">
        <div className="max-w-3xl mx-auto px-4 py-3.5 flex items-center gap-3">
          <div className="p-2 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-xl shadow-sm shadow-blue-200">
            <Heart className="w-4 h-4 text-white fill-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-gray-900">Healthcare AI Triage</h1>
            <p className="text-xs text-gray-400">Patient Symptom Triage</p>
          </div>
          <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-600 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full font-medium">
            <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
            Live
          </span>
        </div>
      </header>

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col min-h-full">
          {isEmpty ? (
            <WelcomeScreen />
          ) : (
            <>
              {messages.map(msg =>
                msg.type === 'user'
                  ? <UserBubble key={msg.id} msg={msg} />
                  : <AssistantBubble key={msg.id} msg={msg} />
              )}
              {loading && <TypingIndicator />}
              {apiError && (
                <div className="flex items-start gap-3 p-3.5 bg-red-50 border border-red-200 rounded-xl mb-4 text-red-700 msg-enter">
                  <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-xs font-semibold">API Error</p>
                    <p className="text-xs mt-0.5">{apiError}</p>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input bar */}
      <div className="flex-shrink-0 bg-white border-t border-gray-200">
        <div className="max-w-3xl mx-auto px-4 py-3">
          {isEmpty && (
            <div className="flex flex-wrap gap-2 mb-3">
              {SAMPLES.map(s => (
                <button
                  key={s}
                  onClick={() => { setInput(s); textareaRef.current?.focus() }}
                  className="text-xs px-3 py-1.5 rounded-full bg-slate-100 hover:bg-blue-50 hover:text-blue-700 text-gray-500 border border-gray-200 hover:border-blue-200 transition-all"
                >
                  {s.length > 44 ? s.slice(0, 44) + '…' : s}
                </button>
              ))}
            </div>
          )}
          <div className="flex items-end gap-3">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe your symptoms or healthcare needs…"
              rows={1}
              className="flex-1 resize-none px-4 py-3 rounded-2xl border border-gray-200 bg-gray-50 focus:bg-white focus:border-blue-400 focus:ring-4 focus:ring-blue-100 outline-none text-sm text-gray-800 placeholder-gray-400 leading-relaxed transition-all overflow-hidden"
              style={{ minHeight: '48px', maxHeight: '144px' }}
            />
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || loading}
              className="flex-shrink-0 w-11 h-11 flex items-center justify-center bg-gradient-to-br from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:from-gray-300 disabled:to-gray-300 disabled:cursor-not-allowed text-white rounded-2xl shadow-sm hover:shadow-md hover:shadow-blue-200 transition-all"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs text-gray-300 text-center mt-2">Enter to send · Shift+Enter for new line</p>
        </div>
      </div>

    </div>
  )
}
