import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box,
  Container,
  Paper,
  Typography,
  Alert,
  CircularProgress,
  Drawer,
  IconButton,
  Fab,
  Snackbar,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  useTheme,
  useMediaQuery,
} from '@mui/material';
import {
  Chat,
  Close,
  ExpandMore,
  SwapVert,
  SwapHoriz,
  Fullscreen,
  FullscreenExit,
} from '@mui/icons-material';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';

import ChatInterface from './ChatInterface';
import { apiService } from '../../services/apiService';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;

const DocumentViewer = () => {
  const { documentId } = useParams();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  // Document state
  const [document, setDocument] = useState(null);
  const [documentFile, setDocumentFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1.0);
  
  // Chat state
  const [chatOpen, setChatOpen] = useState(false);
  const [chatPosition, setChatPosition] = useState('right'); // 'right', 'bottom'
  const [chatSession, setChatSession] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });
  
  // Refs
  const containerRef = useRef(null);
  const pdfContainerRef = useRef(null);

  useEffect(() => {
    const fetchDocument = async () => {
      try {
        setLoading(true);
        
        // Get document info
        const docInfo = await apiService.getDocumentInfo(documentId);
        setDocument(docInfo);
        
        // Check if document is ready for chat
        const chatReady = await apiService.checkDocumentChatReady(documentId);
        if (!chatReady.chat_ready) {
          setSnackbar({
            open: true,
            message: `Document is still processing: ${chatReady.message}`,
            severity: 'warning'
          });
        }
        
        // In a real application, you would fetch the PDF file from your storage
        // For now, we'll simulate loading the PDF
        // setDocumentFile('/path/to/pdf/file.pdf');
        
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

  const onDocumentLoadSuccess = ({ numPages }) => {
    setNumPages(numPages);
  };

  const onDocumentLoadError = (error) => {
    console.error('PDF load error:', error);
    setError('Failed to load PDF document');
  };

  const toggleChat = () => {
    setChatOpen(!chatOpen);
  };

  const toggleChatPosition = () => {
    setChatPosition(prev => prev === 'right' ? 'bottom' : 'right');
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  const handlePageClick = useCallback((pageNum) => {
    setPageNumber(pageNum);
  }, []);

  const handleSourceClick = useCallback((pageNumber, searchText) => {
    if (pageNumber && pageNumber !== pageNumber) {
      setPageNumber(pageNumber);
      
      // Highlight text if possible (this would require more advanced PDF.js integration)
      setSnackbar({
        open: true,
        message: `Navigated to page ${pageNumber}`,
        severity: 'success'
      });
    }
  }, [pageNumber]);

  const getChatDrawerWidth = () => {
    if (chatPosition === 'bottom') return '100%';
    return isMobile ? '100%' : 400;
  };

  const getChatDrawerHeight = () => {
    if (chatPosition === 'bottom') return isMobile ? '50%' : '40%';
    return '100%';
  };

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
        <Alert severity="error">{error}</Alert>
      </Container>
    );
  }

  return (
    <Box ref={containerRef} sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Document Header */}
      <Paper 
        elevation={1} 
        sx={{ 
          p: 2, 
          borderRadius: 0,
          borderBottom: 1,
          borderColor: 'divider',
          zIndex: 10,
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography variant="h6" component="h1">
              {document?.filename || 'Document Viewer'}
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
              {document?.compound && (
                <Chip label={document.compound} size="small" color="primary" />
              )}
              {document?.study_id && (
                <Chip label={document.study_id} size="small" color="secondary" />
              )}
              {document?.deliverable && (
                <Chip label={document.deliverable} size="small" variant="outlined" />
              )}
            </Box>
          </Box>

          <Box sx={{ display: 'flex', gap: 1 }}>
            <IconButton onClick={toggleChatPosition} title="Toggle chat position">
              {chatPosition === 'right' ? <SwapVert  /> : <SwapHoriz  />}
            </IconButton>
            <IconButton onClick={toggleFullscreen} title="Toggle fullscreen">
              {isFullscreen ? <FullscreenExit /> : <Fullscreen />}
            </IconButton>
          </Box>
        </Box>
      </Paper>

      {/* Main Content Area */}
      <Box sx={{ 
        display: 'flex', 
        flexGrow: 1,
        flexDirection: chatPosition === 'bottom' && chatOpen ? 'column' : 'row',
        overflow: 'hidden'
      }}>
        {/* PDF Viewer */}
        <Box 
          ref={pdfContainerRef}
          sx={{ 
            flexGrow: 1,
            overflow: 'auto',
            bgcolor: '#f5f5f5',
            position: 'relative',
            height: chatPosition === 'bottom' && chatOpen ? 'calc(100% - 40%)' : '100%',
          }}
        >
          {documentFile ? (
            <Box sx={{ p: 2, display: 'flex', justifyContent: 'center' }}>
              <Document
                file={documentFile}
                onLoadSuccess={onDocumentLoadSuccess}
                onLoadError={onDocumentLoadError}
                loading={
                  <Box sx={{ textAlign: 'center', p: 4 }}>
                    <CircularProgress />
                    <Typography sx={{ mt: 2 }}>Loading PDF...</Typography>
                  </Box>
                }
              >
                <Page 
                  pageNumber={pageNumber} 
                  scale={scale}
                  renderTextLayer={true}
                  renderAnnotationLayer={true}
                />
              </Document>
            </Box>
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
              <Typography variant="body2" color="text.secondary">
                Document: {document?.filename}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Pages: {document?.total_pages || 'Unknown'}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 2 }}>
                PDF viewing would be implemented with actual file access
              </Typography>
            </Box>
          )}

          {/* Page Navigation */}
          {numPages && (
            <Paper 
              sx={{ 
                position: 'absolute', 
                bottom: 16, 
                left: '50%', 
                transform: 'translateX(-50%)',
                p: 1,
                display: 'flex',
                alignItems: 'center',
                gap: 1,
              }}
            >
              <IconButton 
                size="small" 
                disabled={pageNumber <= 1}
                onClick={() => setPageNumber(prev => Math.max(1, prev - 1))}
              >
                ‹
              </IconButton>
              <Typography variant="body2">
                {pageNumber} of {numPages}
              </Typography>
              <IconButton 
                size="small"
                disabled={pageNumber >= numPages}
                onClick={() => setPageNumber(prev => Math.min(numPages, prev + 1))}
              >
                ›
              </IconButton>
            </Paper>
          )}
        </Box>

        {/* Chat Interface - Drawer Style */}
        <Drawer
          anchor={chatPosition === 'bottom' ? 'bottom' : 'right'}
          open={chatOpen}
          onClose={() => setChatOpen(false)}
          variant="persistent"
          sx={{
            '& .MuiDrawer-paper': {
              width: getChatDrawerWidth(),
              height: getChatDrawerHeight(),
              position: 'relative',
              borderRadius: chatPosition === 'bottom' ? '8px 8px 0 0' : '8px 0 0 8px',
              boxShadow: theme.shadows[8],
            },
          }}
        >
          <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            {/* Chat Header */}
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
              <IconButton 
                size="small" 
                onClick={() => setChatOpen(false)}
                sx={{ color: 'inherit' }}
              >
                <Close />
              </IconButton>
            </Box>

            {/* Chat Interface */}
            <Box sx={{ flexGrow: 1, overflow: 'hidden' }}>
              <ChatInterface 
                documentId={documentId}
                onSourceClick={handleSourceClick}
                chatSession={chatSession}
                setChatSession={setChatSession}
              />
            </Box>
          </Box>
        </Drawer>
      </Box>

      {/* Floating Chat Button */}
      {!chatOpen && (
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

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
        message={snackbar.message}
      />
    </Box>
  );
};

export default DocumentViewer;
