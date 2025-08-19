import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box,
  Container,
  Paper,
  Typography,
  Alert,
  CircularProgress,
  IconButton,
  Fab,
  Snackbar,
  Chip,
  Button,
  useTheme,
  useMediaQuery,
  TextField,
  InputAdornment,
  Toolbar,
  AppBar,
} from '@mui/material';
import {
  Chat,
  Close,
  SwapVert,
  SwapHoriz,
  Refresh,
  Warning,
  Search,
  Clear,
  CheckCircle,
  DragIndicator,
} from '@mui/icons-material';

import ChatInterface from './ChatInterface';
import { apiService } from '../../services/apiService';

const DocumentViewer = () => {
  const { documentId } = useParams();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  // Document state
  const [document, setDocument] = useState(null);
  const [documentFile, setDocumentFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [chatReadiness, setChatReadiness] = useState(null);
  const [pdfLoadError, setPdfLoadError] = useState(false);
  
  // UI state
  const [chatOpen, setChatOpen] = useState(false);
  const [chatPosition, setChatPosition] = useState('right');
  const [chatSession, setChatSession] = useState(null);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });
  const [searchText, setSearchText] = useState('');
  
  // Resizable chat state
  const [chatWidth, setChatWidth] = useState(400);
  const [chatHeight, setChatHeight] = useState(40);
  const [isResizing, setIsResizing] = useState(false);
  
  // Refs
  const containerRef = useRef(null);
  const pdfIframeRef = useRef(null);
  const chatRef = useRef(null);

  useEffect(() => {
    const fetchDocument = async () => {
      try {
        setLoading(true);
        
        const docInfo = await apiService.getDocumentInfo(documentId);
        setDocument(docInfo);
        
        const chatReady = await apiService.checkDocumentChatReady(documentId);
        setChatReadiness(chatReady);
        
        if (docInfo.status === 'completed') {
          const basePath = window.__POSIT_BASE_PATH__ || '';
          const pdfUrl = `${basePath}/api/v1/documents/serve/${documentId}`;
          setDocumentFile(pdfUrl);
        }
        
      } catch (err) {
        setError('Failed to load document: ' + err.message);
        console.error('Error fetching document:', err);
      } finally {
        setLoading(false);
      }
    };

    if (documentId) {
      fetchDocument();
    }
  }, [documentId]);

  // Get PDF.js viewer URL with page parameter
  const getPdfViewerUrl = (pageNumber = null) => {
    if (!documentFile) return '';
    
    const basePath = window.__POSIT_BASE_PATH__ || '';
    const viewerUrl = `${basePath}/static/pdfjs/web/viewer.html`;
    const fileParam = encodeURIComponent(documentFile);
    
    let url = `${viewerUrl}?file=${fileParam}`;
    if (pageNumber) {
      url += `&page=${pageNumber}`;
    }
    
    return url;
  };

  // FIXED: Direct URL-based navigation (most reliable method)
  const navigateToPage = useCallback((pageNumber) => {
    if (!pdfIframeRef.current || !documentFile) {
      console.warn('PDF iframe not ready');
      setSnackbar({
        open: true,
        message: 'PDF viewer not ready yet',
        severity: 'warning'
      });
      return;
    }

    console.log('Navigating to page:', pageNumber);

    try {
      // Direct URL approach - most reliable for PDF.js
      const newUrl = getPdfViewerUrl(pageNumber);
      console.log('Loading PDF with page:', newUrl);
      
      pdfIframeRef.current.src = newUrl;
      
      setSnackbar({
        open: true,
        message: `Navigating to page ${pageNumber}`,
        severity: 'success'
      });
      
    } catch (error) {
      console.error('Navigation failed:', error);
      setSnackbar({
        open: true,
        message: `Failed to navigate to page ${pageNumber}`,
        severity: 'error'
      });
    }
  }, [documentFile]);

  // Search in PDF
  const searchInPdf = useCallback((searchTerm) => {
    if (!pdfIframeRef.current || !documentFile || !searchTerm.trim()) {
      return;
    }

    try {
      console.log('Searching for:', searchTerm);
      
      const basePath = window.__POSIT_BASE_PATH__ || '';
      const viewerUrl = `${basePath}/static/pdfjs/web/viewer.html`;
      const fileParam = encodeURIComponent(documentFile);
      const searchParam = encodeURIComponent(searchTerm.trim());
      const fullUrl = `${viewerUrl}?file=${fileParam}&search=${searchParam}`;
      
      pdfIframeRef.current.src = fullUrl;
      
      setSnackbar({
        open: true,
        message: `Searching for "${searchTerm}"`,
        severity: 'info'
      });
      
    } catch (error) {
      console.error('Search error:', error);
      setSnackbar({
        open: true,
        message: 'Search failed',
        severity: 'error'
      });
    }
  }, [documentFile]);

  // Source click handler
  const handleSourceClick = useCallback((pageNumber) => {
    console.log('Source click - navigating to page:', pageNumber);
    
    if (!pageNumber || typeof pageNumber !== 'number' || pageNumber <= 0) {
      console.warn('Invalid page number:', pageNumber);
      setSnackbar({
        open: true,
        message: `Invalid page number: ${pageNumber}`,
        severity: 'warning'
      });
      return;
    }

    navigateToPage(pageNumber);
  }, [navigateToPage]);

  // FIXED: Working resize handlers
  const handleResizeStart = useCallback((e, direction) => {
    e.preventDefault();
    e.stopPropagation();
    
    console.log('Starting resize:', direction);
    setIsResizing(true);
    
    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = chatWidth;
    const startHeight = chatHeight;
    
    const handleMouseMove = (moveEvent) => {
      if (direction === 'horizontal') {
        // For right panel, decreasing X should increase width
        const deltaX = startX - moveEvent.clientX;
        const newWidth = Math.max(300, Math.min(800, startWidth + deltaX));
        setChatWidth(newWidth);
      } else {
        // For bottom panel, decreasing Y should increase height
        const containerHeight = containerRef.current?.clientHeight || window.innerHeight;
        const deltaY = startY - moveEvent.clientY;
        const newHeightPx = (startHeight / 100) * containerHeight + deltaY;
        const newHeightPercent = Math.max(20, Math.min(70, (newHeightPx / containerHeight) * 100));
        setChatHeight(newHeightPercent);
      }
    };
    
    const handleMouseUp = () => {
      console.log('Ending resize');
      setIsResizing(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = direction === 'horizontal' ? 'col-resize' : 'row-resize';
    document.body.style.userSelect = 'none';
  }, [chatWidth, chatHeight]);

  // Cleanup resize on unmount
  useEffect(() => {
    return () => {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, []);

  const handleSearch = (text) => {
    setSearchText(text);
    if (text.trim()) {
      searchInPdf(text);
    }
  };

  const toggleChat = () => {
    if (!chatReadiness?.chat_ready) {
      setSnackbar({
        open: true,
        message: 'Chat is not available for this document',
        severity: 'warning'
      });
      return;
    }
    setChatOpen(!chatOpen);
  };

  const toggleChatPosition = () => {
    setChatPosition(prev => prev === 'right' ? 'bottom' : 'right');
  };

  const getChatDrawerWidth = () => {
    if (chatPosition === 'bottom') return '100%';
    return isMobile ? '100%' : `${chatWidth}px`;
  };

  const getChatDrawerHeight = () => {
    if (chatPosition === 'bottom') return `${chatHeight}%`;
    return '100%';
  };

  // Setup instructions component
  const SetupInstructions = () => (
    <Alert severity="error" sx={{ m: 2 }}>
      <Typography variant="h6" gutterBottom>
        PDF Viewer Failed to Load
      </Typography>
      <Typography variant="body2" gutterBottom>
        The PDF.js viewer couldn't be loaded. Please ensure you have set up the PDF.js files:
      </Typography>
      <Box component="ol" sx={{ pl: 2, mt: 1 }}>
        <li>Check that the following files exist in your frontend directory:</li>
        <Box component="pre" sx={{ 
          bgcolor: 'grey.100', 
          p: 1, 
          borderRadius: 1, 
          fontSize: '0.85rem',
          my: 1,
          overflow: 'auto'
        }}>
{`frontend/public/static/pdfjs/web/viewer.html
frontend/public/static/pdfjs/build/pdf.js
frontend/public/static/pdfjs/build/pdf.worker.js`}
        </Box>
        <li>If missing, run this setup command:</li>
        <Box component="pre" sx={{ 
          bgcolor: 'grey.100', 
          p: 1, 
          borderRadius: 1, 
          fontSize: '0.85rem',
          my: 1,
          overflow: 'auto'
        }}>
{`cd frontend
curl -L "https://github.com/mozilla/pdf.js/releases/download/v4.0.379/pdfjs-4.0.379-dist.zip" -o pdfjs-dist.zip
unzip pdfjs-dist.zip -d temp-pdfjs
mkdir -p public/static/pdfjs
mv temp-pdfjs/* public/static/pdfjs/
rm -rf temp-pdfjs pdfjs-dist.zip`}
        </Box>
        <li>Restart your server and refresh this page</li>
      </Box>
    </Alert>
  );

  // FIXED: Working resize handle component
  const ResizeHandle = ({ direction }) => (
    <Box
      onMouseDown={(e) => handleResizeStart(e, direction)}
      sx={{
        position: 'absolute',
        ...(direction === 'horizontal' ? {
          left: -3,
          top: 0,
          width: 6,
          height: '100%',
          cursor: 'col-resize',
        } : {
          top: -3,
          left: 0,
          width: '100%',
          height: 6,
          cursor: 'row-resize',
        }),
        bgcolor: 'rgba(0, 0, 0, 0.1)',
        zIndex: 1001,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        '&:hover': {
          bgcolor: 'primary.main',
          opacity: 0.7,
        },
        '&:active': {
          bgcolor: 'primary.main',
          opacity: 0.9,
        },
      }}
    >
      <DragIndicator 
        sx={{ 
          color: 'white',
          transform: direction === 'horizontal' ? 'rotate(90deg)' : 'none',
          fontSize: 14,
        }} 
      />
    </Box>
  );

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, textAlign: 'center' }}>
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ mt: 2 }}>
          Loading document...
        </Typography>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
        <Button onClick={() => window.location.reload()} startIcon={<Refresh />}>
          Retry
        </Button>
      </Container>
    );
  }

  return (
    <Box 
      ref={containerRef} 
      sx={{ 
        height: '100vh', 
        display: 'flex', 
        flexDirection: 'column', 
        overflow: 'hidden',
        userSelect: isResizing ? 'none' : 'auto'
      }}
    >
      {/* Document Header */}
      <AppBar position="static" color="default" elevation={1}>
        <Toolbar variant="dense">
          <Box sx={{ display: 'flex', alignItems: 'center', flexGrow: 1 }}>
            <Typography variant="h6" sx={{ mr: 2, flexShrink: 0 }}>
              {document?.filename || 'Document Viewer'}
            </Typography>
            
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexShrink: 0 }}>
              {document?.compound && (
                <Chip label={document.compound} size="small" color="primary" />
              )}
              {document?.study_id && (
                <Chip label={document.study_id} size="small" color="secondary" />
              )}
              {chatReadiness && (
                <Chip 
                  label={chatReadiness.chat_ready ? 'Chat Ready' : 'Chat Unavailable'} 
                  size="small" 
                  color={chatReadiness.chat_ready ? 'success' : 'warning'}
                  variant="outlined"
                  icon={chatReadiness.chat_ready ? undefined : <Warning />}
                />
              )}
              {documentFile && !pdfLoadError && (
                <Chip 
                  label="Viewer Ready" 
                  size="small" 
                  color="success"
                  variant="outlined"
                  icon={<CheckCircle />}
                />
              )}
            </Box>
          </Box>

          {/* Action Buttons */}
          <Box sx={{ display: 'flex', gap: 1 }}>
            <IconButton onClick={() => window.location.reload()} title="Refresh document">
              <Refresh />
            </IconButton>
            {chatOpen && (
              <IconButton onClick={toggleChatPosition} title="Toggle chat position">
                {chatPosition === 'right' ? <SwapVert /> : <SwapHoriz />}
              </IconButton>
            )}
          </Box>
        </Toolbar>
      </AppBar>

      {/* Search Bar */}
      {documentFile && !pdfLoadError && (
        <Paper elevation={0} sx={{ borderBottom: 1, borderColor: 'divider', p: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TextField
              size="small"
              placeholder="Search in document..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  handleSearch(searchText);
                }
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search />
                  </InputAdornment>
                ),
                endAdornment: searchText && (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setSearchText('')}>
                      <Clear />
                    </IconButton>
                  </InputAdornment>
                )
              }}
              sx={{ flexGrow: 1, maxWidth: 400 }}
            />
            
            <Button 
              variant="outlined" 
              size="small" 
              onClick={() => handleSearch(searchText)}
              disabled={!searchText.trim()}
            >
              Search
            </Button>
          </Box>
        </Paper>
      )}

      {/* Main Content Area */}
      <Box sx={{ 
        display: 'flex', 
        flexGrow: 1,
        flexDirection: chatPosition === 'bottom' && chatOpen ? 'column' : 'row',
        overflow: 'hidden',
        position: 'relative'
      }}>
        {/* PDF Viewer */}
        <Box 
          sx={{ 
            flexGrow: 1,
            overflow: 'hidden',
            position: 'relative',
            height: chatPosition === 'bottom' && chatOpen ? `calc(100% - ${chatHeight}%)` : '100%',
            width: chatPosition === 'right' && chatOpen ? `calc(100% - ${chatWidth}px)` : '100%',
            transition: isResizing ? 'none' : 'all 0.2s ease',
          }}
        >
          {pdfLoadError ? (
            <SetupInstructions />
          ) : documentFile ? (
            <iframe
              ref={pdfIframeRef}
              src={getPdfViewerUrl()}
              width="100%"
              height="100%"
              style={{ border: 'none' }}
              title="PDF Viewer"
              onLoad={() => {
                console.log('PDF viewer loaded');
                setPdfLoadError(false);
                setSnackbar({
                  open: true,
                  message: 'PDF loaded successfully',
                  severity: 'success'
                });
              }}
              onError={() => {
                console.error('PDF viewer load error');
                setPdfLoadError(true);
                setSnackbar({
                  open: true,
                  message: 'Failed to load PDF viewer',
                  severity: 'error'
                });
              }}
            />
          ) : (
            <Box sx={{ 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              height: '100%',
              flexDirection: 'column'
            }}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                PDF Viewer
              </Typography>
              <Typography variant="body1" sx={{ mb: 1 }}>
                Document: {document?.filename}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Status: {document?.status}
              </Typography>
              
              {document?.status === 'completed' && (
                <Alert severity="info" sx={{ mt: 2, maxWidth: 400 }}>
                  Document processed but PDF viewing is not available.
                </Alert>
              )}
              
              {document?.status !== 'completed' && (
                <Alert severity="warning" sx={{ mt: 2, maxWidth: 400 }}>
                  Document is still being processed.
                </Alert>
              )}
            </Box>
          )}
        </Box>

        {/* Resizable Chat Interface */}
        {chatReadiness?.chat_ready && chatOpen && (
          <Box
            ref={chatRef}
            sx={{
              position: 'relative',
              width: getChatDrawerWidth(),
              height: getChatDrawerHeight(),
              backgroundColor: 'background.paper',
              borderRadius: chatPosition === 'bottom' ? '8px 8px 0 0' : '8px 0 0 8px',
              boxShadow: theme.shadows[8],
              transition: isResizing ? 'none' : 'all 0.2s ease',
              zIndex: 1200,
              ...(chatPosition === 'right' && {
                borderLeft: 1,
                borderColor: 'divider',
              }),
              ...(chatPosition === 'bottom' && {
                borderTop: 1,
                borderColor: 'divider',
              }),
            }}
          >
            {/* Resize Handle */}
            <ResizeHandle direction={chatPosition === 'right' ? 'horizontal' : 'vertical'} />

            {/* Chat Content */}
            <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
              <Box sx={{ 
                p: 2, 
                borderBottom: 1, 
                borderColor: 'divider',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                bgcolor: 'primary.main',
                color: 'primary.contrastText',
              }}>
                <Typography variant="h6">
                  Document Chat
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <IconButton 
                    size="small" 
                    onClick={toggleChatPosition}
                    sx={{ color: 'inherit' }}
                    title="Toggle position"
                  >
                    {chatPosition === 'right' ? <SwapVert /> : <SwapHoriz />}
                  </IconButton>
                  <IconButton 
                    size="small" 
                    onClick={() => setChatOpen(false)}
                    sx={{ color: 'inherit' }}
                  >
                    <Close />
                  </IconButton>
                </Box>
              </Box>

              <Box sx={{ flexGrow: 1, overflow: 'hidden' }}>
                <ChatInterface 
                  documentId={documentId}
                  onSourceClick={handleSourceClick}
                  onSearchInDocument={handleSearch}
                  chatSession={chatSession}
                  setChatSession={setChatSession}
                />
              </Box>
            </Box>
          </Box>
        )}
      </Box>

      {/* Floating Action Button */}
      {!chatOpen && chatReadiness?.chat_ready && (
        <Fab
          color="primary"
          onClick={toggleChat}
          sx={{
            position: 'fixed',
            bottom: 16,
            right: 16,
            zIndex: 1000,
          }}
        >
          <Chat />
        </Fab>
      )}

      {/* Chat Unavailable Info */}
      {!chatReadiness?.chat_ready && (
        <Fab
          color="default"
          onClick={() => setSnackbar({
            open: true,
            message: chatReadiness?.message || 'Chat functionality is not available',
            severity: 'info'
          })}
          sx={{
            position: 'fixed',
            bottom: 16,
            right: 16,
            zIndex: 1000,
          }}
        >
          <Warning />
        </Fab>
      )}

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert 
          severity={snackbar.severity} 
          onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default DocumentViewer;
