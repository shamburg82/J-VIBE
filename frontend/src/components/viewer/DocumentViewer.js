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
  const [pdfLoaded, setPdfLoaded] = useState(false);
  
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
  const resizeOverlayRef = useRef(null);
  const isMountedRef = useRef(true);
  const cleanupRef = useRef(false);

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

  // Get PDF.js viewer URL
  const getPdfViewerUrl = () => {
    if (!documentFile) return '';
    
    const basePath = window.__POSIT_BASE_PATH__ || '';
    const viewerUrl = `${basePath}/static/pdfjs/web/viewer.html`;
    const fileParam = encodeURIComponent(documentFile);
    
    return `${viewerUrl}?file=${fileParam}`;
  };

  // Helper to inject navigation script into PDF.js viewer
  const injectPdfNavigationHelper = useCallback(() => {
    if (!pdfIframeRef.current) return;
    
    try {
      const iframe = pdfIframeRef.current;
      
      // Inject a helper function into the PDF viewer
      const script = iframe.contentDocument.createElement('script');
      script.textContent = `
        // Helper for external navigation
        window.addEventListener('message', function(e) {
          if (e.data && e.data.type === 'goToPage' && e.data.page) {
            if (window.PDFViewerApplication && window.PDFViewerApplication.pdfViewer) {
              window.PDFViewerApplication.page = e.data.page;
              // Also try to center the page
              window.PDFViewerApplication.pdfViewer.scrollPageIntoView({
                pageNumber: e.data.page,
                destArray: [null, { name: "FitH" }]
              });
            }
          }
        });
        
        // Listen for hash changes
        window.addEventListener('hashchange', function() {
          const hash = window.location.hash.substring(1);
          const params = new URLSearchParams(hash);
          const page = params.get('page');
          if (page && window.PDFViewerApplication) {
            window.PDFViewerApplication.page = parseInt(page);
          }
        });
      `;
      iframe.contentDocument.body.appendChild(script);
      console.log('Injected PDF navigation helper');
    } catch (e) {
      console.log('Could not inject navigation helper:', e);
    }
  }, []);

  // Navigate to page without reloading the entire PDF
  const navigateToPage = useCallback((pageNumber) => {
    if (!pdfIframeRef.current || !documentFile || !isMountedRef.current) {
      console.warn('PDF iframe not ready or component unmounted');
      if (isMountedRef.current) {
        setSnackbar({
          open: true,
          message: 'PDF viewer not ready yet',
          severity: 'warning'
        });
      }
      return;
    }

    console.log('Navigating to page:', pageNumber);

    try {
      const iframe = pdfIframeRef.current;
      
      // Method 1: Try hash navigation first (doesn't reload PDF)
      try {
        // Update hash without reloading
        const newHash = `#page=${pageNumber}&zoom=page-fit`;
        iframe.contentWindow.location.hash = newHash;
        
        // Also try direct PDFViewerApplication access
        setTimeout(() => {
          try {
            if (iframe.contentWindow && iframe.contentWindow.PDFViewerApplication) {
              iframe.contentWindow.PDFViewerApplication.page = pageNumber;
              // Try to scroll to top of page
              if (iframe.contentWindow.PDFViewerApplication.pdfViewer) {
                iframe.contentWindow.PDFViewerApplication.pdfViewer.scrollPageIntoView({
                  pageNumber: pageNumber,
                  destArray: [null, { name: "FitH" }]
                });
              }
            }
          } catch (e) {
            console.log('Direct PDFViewerApplication access failed:', e);
          }
        }, 100);
        
      } catch (hashError) {
        console.log('Hash navigation failed, trying postMessage');
        
        // Method 2: PostMessage as fallback
        iframe.contentWindow.postMessage({
          type: 'goToPage',
          page: pageNumber
        }, '*');
      }
      
      if (isMountedRef.current) {
        setSnackbar({
          open: true,
          message: `Navigating to page ${pageNumber}`,
          severity: 'success'
        });
      }
      
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
      
      const iframe = pdfIframeRef.current;
      
      // Try to trigger search in PDF.js
      // Approach 1: Use hash parameter
      iframe.contentWindow.location.hash = `search=${encodeURIComponent(searchTerm)}`;
      
      // Approach 2: PostMessage
      iframe.contentWindow.postMessage({
        type: 'search',
        query: searchTerm
      }, '*');
      
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

  // Resize handler with overlay
  const handleResizeStart = useCallback((e) => {
    if (!isMountedRef.current) return;

    // Get direction from data attribute
    const direction = e.currentTarget.dataset.direction;
    
    if (!direction) {
      console.error('No resize direction specified');
      return;
    }
    
    // Prevent default behaviors
    e.preventDefault();
    e.stopPropagation();
    
    console.log('Starting resize:', direction);
    setIsResizing(true);
    
    const startX = e.clientX || (e.touches && e.touches[0].clientX);
    const startY = e.clientY || (e.touches && e.touches[0].clientY);
    const startWidth = chatWidth;
    const startHeight = chatHeight;
    
    // Create overlay to prevent iframe interference
    if (!resizeOverlayRef.current) {
      const overlay = document.createElement('div');
      overlay.id = 'resize-overlay';
      overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 9999;
        cursor: ${direction === 'horizontal' ? 'col-resize' : 'row-resize'};
        background-color: transparent;
        user-select: none;
      `;
      document.body.appendChild(overlay);
      resizeOverlayRef.current = overlay;
    }
    
    const handleMove = (moveEvent) => {
      if (!isMountedRef.current) return;

      moveEvent.preventDefault();
      const clientX = moveEvent.clientX || (moveEvent.touches && moveEvent.touches[0].clientX);
      const clientY = moveEvent.clientY || (moveEvent.touches && moveEvent.touches[0].clientY);
      
      if (direction === 'horizontal') {
        const deltaX = startX - clientX;
        const newWidth = Math.max(300, Math.min(800, startWidth + deltaX));
        if (isMountedRef.current) {
          setChatWidth(newWidth);
        }
      } else {
        const containerHeight = containerRef.current?.clientHeight || window.innerHeight;
        const deltaY = startY - clientY;
        const newHeightPx = (startHeight / 100) * containerHeight + deltaY;
        const newHeightPercent = Math.max(20, Math.min(70, (newHeightPx / containerHeight) * 100));
        if (isMountedRef.current) {
          setChatHeight(newHeightPercent);
        }
      }
    };
    
    const handleEnd = () => {
      console.log('Ending resize');
    
      if (isMountedRef.current) {
        setIsResizing(false);
      }
      
      // Remove overlay
      if (resizeOverlayRef.current) {
        resizeOverlayRef.current.remove();
        resizeOverlayRef.current = null;
      }
      
      // Clean up event listeners
      document.removeEventListener('mousemove', handleMove);
      document.removeEventListener('mouseup', handleEnd);
      document.removeEventListener('touchmove', handleMove);
      document.removeEventListener('touchend', handleEnd);
      
      // Reset cursor
      if (document.body) {
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    
    // Add event listeners
    document.addEventListener('mousemove', handleMove);
    document.addEventListener('mouseup', handleEnd);
    document.addEventListener('touchmove', handleMove, { passive: false });
    document.addEventListener('touchend', handleEnd);
    
    // Set cursor
    if (document.body) {
      document.body.style.cursor = direction === 'horizontal' ? 'col-resize' : 'row-resize';
      document.body.style.userSelect = 'none';
    }
  }, [chatWidth, chatHeight]);

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    
    return () => {
      console.log('DocumentViewer unmounting, cleaning up...');
      isMountedRef.current = false;
      cleanupRef.current = true;
      
      // Clean up resize overlay if it exists
      if (resizeOverlayRef.current) {
        resizeOverlayRef.current.remove();
        resizeOverlayRef.current = null;
      }
      
      // Reset body styles
      if (document.body) {
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
      
      // Clear any pending timeouts
      const highestId = window.setTimeout(() => {}, 0);
      for (let i = 0; i < highestId; i++) {
        window.clearTimeout(i);
      }
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

  // Resize handle component
  const ResizeHandle = ({ direction }) => (
    <Box
      data-direction={direction}
      onMouseDown={handleResizeStart}
      onTouchStart={handleResizeStart}
      sx={{
        position: 'absolute',
        ...(direction === 'horizontal' ? {
          left: -6,
          top: 0,
          width: 12,
          height: '100%',
          cursor: 'col-resize',
        } : {
          top: -6,
          left: 0,
          width: '100%',
          height: 12,
          cursor: 'row-resize',
        }),
        bgcolor: 'transparent',
        zIndex: 1300,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        '&:hover': {
          bgcolor: 'rgba(25, 118, 210, 0.1)',
        },
        // Visible grip line
        '&::before': {
          content: '""',
          position: 'absolute',
          bgcolor: 'divider',
          ...(direction === 'horizontal' ? {
            left: '50%',
            transform: 'translateX(-50%)',
            width: 3,
            height: '100%',
          } : {
            top: '50%',
            transform: 'translateY(-50%)',
            width: '100%',
            height: 3,
          }),
        },
      }}
    >
      <DragIndicator 
        sx={{ 
          color: 'action.active',
          transform: direction === 'horizontal' ? 'rotate(90deg)' : 'none',
          fontSize: 18,
          pointerEvents: 'none',
          opacity: 0.7,
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
        overflow: 'hidden'
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
              {documentFile && !pdfLoadError && pdfLoaded && (
                <Chip 
                  label="PDF Ready" 
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
        {/* PDF Viewer - FIXED: removed pointerEvents style */}
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
            <Alert severity="error" sx={{ m: 2 }}>
              <Typography variant="h6" gutterBottom>
                PDF Viewer Failed to Load
              </Typography>
              <Typography variant="body2" gutterBottom>
                The PDF.js viewer couldn't be loaded. Please ensure you have set up the PDF.js files.
              </Typography>
            </Alert>
          ) : documentFile ? (
            <iframe
              ref={pdfIframeRef}
              src={getPdfViewerUrl()}
              width="100%"
              height="100%"
              style={{ border: 'none' }}
              title="PDF Viewer"
              onLoad={() => {
                console.log('PDF viewer iframe loaded');
                setPdfLoadError(false);
                setPdfLoaded(true);
                
                // Inject navigation helper after a delay
                setTimeout(() => {
                  injectPdfNavigationHelper();
                }, 500);
                
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
