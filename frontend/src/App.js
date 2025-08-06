import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { CssBaseline, Box } from '@mui/material';

// Components
import Navbar from './components/layout/Navbar';
import CompoundList from './components/viewer/CompoundList';
import StudyList from './components/viewer/StudyList';
import DeliverableList from './components/viewer/DeliverableList';
import DocumentList from './components/viewer/DocumentList';
import DocumentViewer from './components/viewer/DocumentViewer';
import AdminDashboard from './components/admin/AdminDashboard';
import DocumentUpload from './components/admin/DocumentUpload';
import DocumentManagement from './components/admin/DocumentManagement';

// Services
import { apiService } from './services/apiService';

// Theme configuration
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
      light: '#42a5f5',
      dark: '#1565c0',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
      paper: '#ffffff',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 500,
    },
    h6: {
      fontWeight: 500,
    },
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          borderRadius: 8,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 6,
        },
      },
    },
  },
});

function App() {
  const [userRole, setUserRole] = useState('viewer'); // 'viewer' or 'admin'
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Check user permissions and app health
    const initializeApp = async () => {
      try {
        setIsLoading(true);
        
        // Check API health
        await apiService.checkHealth();
        
        // In a real app, you'd check user permissions here
        // For now, we'll simulate based on environment or URL params
        const urlParams = new URLSearchParams(window.location.search);
        const roleParam = urlParams.get('role');
        
        if (roleParam === 'admin') {
          setUserRole('admin');
        } else {
          setUserRole('viewer');
        }
        
      } catch (err) {
        setError('Failed to connect to TLF Analyzer API');
        console.error('App initialization error:', err);
      } finally {
        setIsLoading(false);
      }
    };

    initializeApp();
  }, []);

  if (isLoading) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box 
          display="flex" 
          justifyContent="center" 
          alignItems="center" 
          minHeight="100vh"
          bgcolor="background.default"
        >
          <div>Loading TLF Analyzer...</div>
        </Box>
      </ThemeProvider>
    );
  }

  if (error) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box 
          display="flex" 
          justifyContent="center" 
          alignItems="center" 
          minHeight="100vh"
          bgcolor="background.default"
        >
          <div style={{ textAlign: 'center', color: 'red' }}>
            <h2>Connection Error</h2>
            <p>{error}</p>
            <button onClick={() => window.location.reload()}>Retry</button>
          </div>
        </Box>
      </ThemeProvider>
    );
  }

  // Get the base path for routing
  const basePath = window.__POSIT_BASE_PATH__ || '';

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router basename={basePath}>
        <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
          <Navbar userRole={userRole} />
          
          <Box sx={{ flexGrow: 1, bgcolor: 'background.default' }}>
            <Routes>
              {/* Viewer Routes */}
              <Route path="/" element={<Navigate to="/compounds" replace />} />
              <Route path="/compounds" element={<CompoundList />} />
              <Route path="/compounds/:compound/studies" element={<StudyList />} />
              <Route 
                path="/compounds/:compound/studies/:studyId/deliverables" 
                element={<DeliverableList />} 
              />
              <Route 
                path="/compounds/:compound/studies/:studyId/deliverables/:deliverable/documents" 
                element={<DocumentList />} 
              />
              <Route path="/documents/:documentId" element={<DocumentViewer />} />
              
              {/* Admin Routes - Only accessible if user has admin role */}
              {userRole === 'admin' && (
                <>
                  <Route path="/admin" element={<AdminDashboard />} />
                  <Route path="/admin/upload" element={<DocumentUpload />} />
                  <Route path="/admin/manage" element={<DocumentManagement />} />
                </>
              )}
              
              {/* Catch all - redirect to compounds */}
              <Route path="*" element={<Navigate to="/compounds" replace />} />
            </Routes>
          </Box>
        </Box>
      </Router>
    </ThemeProvider>
  );
}

export default App;
