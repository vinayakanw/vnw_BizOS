import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import { AuthProvider, hint, useAuth } from './lib/auth'
import AuthPage from './pages/AuthPage'
import Landing from './pages/Landing'
import Activity from './pages/Activity'
import Analytics from './pages/Analytics'
import Approvals from './pages/Approvals'
import Dashboard from './pages/Dashboard'
import LeadDetail from './pages/LeadDetail'
import Leads from './pages/Leads'
import SalesAgent from './pages/SalesAgent'
import Documents from './pages/Documents'
import Faqs from './pages/Faqs'
import Knowledge from './pages/Knowledge'
import Products from './pages/Products'
import Workflows from './pages/Workflows'
import Profile from './pages/Profile'
import Founder from './pages/Founder'
import CustomerChat from './pages/CustomerChat'
import Inbox from './pages/Inbox'
import InboxDetail from './pages/InboxDetail'
import PublicChat from './pages/PublicChat'
import PublicQuote from './pages/PublicQuote'
import Orders from './pages/Orders'
import Integrations from './pages/Integrations'
import SupportAgent from './pages/SupportAgent'
import Tickets from './pages/Tickets'
import TicketDetail from './pages/TicketDetail'

function Protected({ children }: { children: React.ReactNode }) {
  const { me, loading, offline, retry } = useAuth()
  const home = useLocation().pathname === '/'
  // first-time visitors see the landing page at once, even while a sleeping server wakes up
  if (loading && home && !hint()) return <Landing />
  if (loading) return <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">Loading...</div>
  if (offline && !(home && !hint())) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-center">
        <div className="max-w-sm">
          <p className="font-display text-xl font-bold">Can't reach BizOS</p>
          <p className="mt-2 text-sm text-slate-600">Your internet may be down, or the server is busy. You are still signed in.</p>
          <button onClick={retry} className="mt-4 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700">Try again</button>
        </div>
      </div>
    )
  }
  if (!me) return home ? <Landing /> : <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/register" element={<AuthPage mode="register" />} />
          <Route path="/chat/:slug" element={<PublicChat />} />
          <Route path="/quote/:token" element={<PublicQuote />} />
          <Route element={<Protected><Layout /></Protected>}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/sales-agent" element={<SalesAgent />} />
            <Route path="/integrations" element={<Integrations />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/inbox/:id" element={<InboxDetail />} />
            <Route path="/customer-chat" element={<CustomerChat />} />
            <Route path="/founder" element={<Founder />} />
            <Route path="/support-agent" element={<SupportAgent />} />
            <Route path="/tickets" element={<Tickets />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/tickets/:id" element={<TicketDetail />} />
            <Route path="/leads" element={<Leads />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/leads/:id" element={<LeadDetail />} />
            <Route path="/workflows" element={<Workflows />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/activity" element={<Activity />} />
            <Route path="/products" element={<Products />} />
            <Route path="/faqs" element={<Faqs />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/profile" element={<Profile />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
