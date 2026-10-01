import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import Layout from './components/Layout';
import Login from './pages/Login';
import Ops from './pages/Ops';
import Boxes from './pages/Boxes';
import BoxDetail from './pages/BoxDetail';
import Inbox from './pages/Inbox';
import MessageView from './pages/MessageView';
import Compose from './pages/Compose';
import Queue from './pages/Queue';
import Addrbook from './pages/Addrbook';
import Files from './pages/Files';

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <PrivateRoute>
            <Layout>
              <Routes>
                <Route index element={<Navigate to="/ops" replace />} />
                <Route path="ops" element={<Ops />} />
                <Route path="boxes" element={<Boxes />} />
                <Route path="boxes/:boxId" element={<BoxDetail />} />
                <Route path="mail/:boxId/inbox" element={<Inbox />} />
                <Route path="mail/:boxId/inbox/:messageId" element={<MessageView />} />
                <Route path="mail/:boxId/compose" element={<Compose />} />
                <Route path="queue" element={<Queue />} />
                <Route path="addrbook" element={<Addrbook />} />
                <Route path="files/:boxId" element={<Files />} />
              </Routes>
            </Layout>
          </PrivateRoute>
        }
      />
    </Routes>
  );
}
