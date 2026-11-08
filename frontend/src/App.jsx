import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout.jsx'
import { HoldPage } from './pages/HoldPage.jsx'
import { HoldReviewPage } from './pages/HoldReviewPage.jsx'
import { LaundromatSlotsPage } from './pages/LaundromatSlotsPage.jsx'
import { LaundromatsPage } from './pages/LaundromatsPage.jsx'
import { LoginPage } from './pages/LoginPage.jsx'
import { NotFoundPage } from './pages/NotFoundPage.jsx'
import { OperatorNotificationsPage } from './pages/OperatorNotificationsPage.jsx'
import { OperatorPage } from './pages/OperatorPage.jsx'
import { OperatorTodayPage } from './pages/OperatorTodayPage.jsx'
import { RegisterPage } from './pages/RegisterPage.jsx'
import { ReservationsPage } from './pages/ReservationsPage.jsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/laundromats" replace />} />
        {/* Shared file: add one Route line per page. Fill in src/pages/. */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/laundromats" element={<LaundromatsPage />} />
        <Route path="/laundromats/:id" element={<LaundromatSlotsPage />} />
        <Route path="/slots/:slotId/hold" element={<HoldPage />} />
        <Route path="/holds/:holdId" element={<HoldReviewPage />} />
        <Route path="/reservations" element={<ReservationsPage />} />
        <Route path="/operator" element={<OperatorPage />} />
        <Route path="/operator/today" element={<OperatorTodayPage />} />
        <Route path="/operator/notifications" element={<OperatorNotificationsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
