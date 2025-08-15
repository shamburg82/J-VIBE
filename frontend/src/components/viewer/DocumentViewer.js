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
  Button,
  useTheme,
  useMediaQuery,
  TextField,
  InputAdornment,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  ListItemIcon,
  Collapse,
  Divider,
  Toolbar,
  AppBar,
  Slider,
  FormControl,
  Select,
  MenuItem,
  InputLabel,
  Tooltip,
  Badge,
} from '@mui/material';
import {
  Chat,
  Close,
  SwapVert,
  SwapHoriz,
  Fullscreen,
  FullscreenExit,
  Refresh,
  Warning,
  Search,
  Bookmark,
  ZoomIn,
  ZoomOut,
  FitScreen,
  NavigateBefore,
  NavigateNext,
  FirstPage,
  LastPage,
  ExpandLess,
  ExpandMore,
  Article,
  Clear,
  FindInPage,
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
  const [pdfDocument, setPdfDocument] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1.0);
  const [chatReadiness, setChatReadiness] = useState(null);
  
  // PDF features state
  const [bookmarks, setBookmarks] = useState([]);
  const [expandedBookmarks, setExpandedBookmarks] = useState(new Set());
  const [searchText, setSearchText] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [currentSearchResult, setCurrentSearchResult] = useState(0);
  const [searching, setSearching] = useState(false);
  const [pageText, setPageText] = useState(new Map()); // Cache for page text content
  
  // UI state
  const [chatOpen, setChatOpen] = useState(false);
  const [bookmarksOpen, setBookmarksOpen] = useState(true);
  const [chatPosition, setChatPosition] = useState('right');
  const [chatSession, setChatSession] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });
  const [viewMode, setViewMode] = useState('fitWidth'); // 'fitWidth', 'fitPage', 'actualSize'
  
  // Refs
  const containerRef = useRef(null);
  const pageRefs = useRef(new Map());
  const searchTimeoutRef = useRef(null);
  const scrollContainerRef = useRef(null);

  // Scroll listener to update current page
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer || !numPages) return;

    let isNavigating = false; // Flag to prevent interference during programmatic navigation

    const handleScroll = () => {
      if (scrollContainer._isNavigating) return; // Skip if we're in the middle of programmatic navigation
      
      const scrollTop = scrollContainer.scrollTop;
      const containerHeight = scrollContainer.clientHeight;
      const scrollCenter = scrollTop + containerHeight / 2;

      // Find which page is currently in the center of the view
      for (let i = 1; i <= numPages; i++) {
        const pageElement = document.getElementById(`page-${i}`);
        if (pageElement) {
          const rect = pageElement.getBoundingClientRect();
          const containerRect = scrollContainer.getBoundingClientRect();
          const pageTop = rect.top - containerRect.top + scrollTop;
          const pageBottom = pageTop + rect.height;

          if (scrollCenter >= pageTop && scrollCenter <= pageBottom) {
            if (pageNumber !== i) {
              setPageNumber(i);
            }
            break;
          }
        }
      }
    };

    const throttledScroll = throttle(handleScroll, 100);
    scrollContainer.addEventListener('scroll', throttledScroll);

    // Expose the isNavigating flag globally so navigateToPage can use it
    scrollContainer._isNavigating = false;

    return () => {
      scrollContainer.removeEventListener('scroll', throttledScroll);
    };
  }, [numPages, pageNumber]);

  // Throttle function
  const throttle = (func, limit) => {
    let inThrottle;
    return function() {
      const args = arguments;
      const context = this;
      if (!inThrottle) {
        func.apply(context, args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  };

  useEffect(() => {
    const fetchDocument = async () => {
      try {
        setLoading(true);
        
        const docInfo = await apiService.getDocumentInfo(documentId);
        setDocument(docInfo);
        
        const chatReady = await apiService.checkDocumentChatReady(documentId);
        setChatReadiness(chatReady);
        
        if (!chatReady.chat_ready) {
          setSnackbar({
            open: true,
            message: chatReady.message,
            severity: chatReady.status === 'no_index' ? 'warning' : 'info'
          });
        }
        
        if (docInfo.status === 'completed') {
          try {
            const basePath = window.__POSIT_BASE_PATH__ || '';
            const pdfUrl = `${basePath}/api/v1/documents/serve/${documentId}`;
            
            const response = await fetch(pdfUrl, { method: 'HEAD' });
            if (response.ok) {
              setDocumentFile(pdfUrl);
            } else {
              console.warn('PDF file not accessible via server:', response.status);
              setSnackbar({
                open: true,
                message: 'PDF file not available for viewing, but document metadata is accessible',
                severity: 'warning'
              });
            }
          } catch (pdfError) {
            console.warn('Could not access PDF file:', pdfError);
            setSnackbar({
              open: true,
              message: 'PDF file not available for viewing, but document metadata is accessible',
              severity: 'warning'
            });
          }
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

  const onDocumentLoadSuccess = async (pdf) => {
    setPdfDocument(pdf);
    setNumPages(pdf.numPages);
    
    // Extract bookmarks/outline
    try {
      const outline = await pdf.getOutline();
      if (outline) {
        const processedBookmarks = await processBookmarks(outline, pdf);
        setBookmarks(processedBookmarks);
      }
    } catch (err) {
      console.warn('Could not extract bookmarks:', err);
    }
    
    setSnackbar({
      open: true,
      message: `PDF loaded successfully (${pdf.numPages} pages)`,
      severity: 'success'
    });
  };

  const processBookmarks = async (outline, pdf) => {
    const processItem = async (item, level = 0) => {
      let pageNum = null;
      
      // Try to resolve destination to page number
      if (item.dest) {
        try {
          let dest = item.dest;
          if (typeof dest === 'string') {
            dest = await pdf.getDestination(dest);
          }
          if (dest && dest[0]) {
            const pageRef = dest[0];
            const pageIndex = await pdf.getPageIndex(pageRef);
            pageNum = pageIndex + 1;
          }
        } catch (err) {
          console.warn('Could not resolve bookmark destination:', err);
        }
      }
      
      const bookmark = {
        title: item.title,
        pageNumber: pageNum,
        level,
        id: `bookmark_${Math.random().toString(36).substr(2, 9)}`,
        children: []
      };
      
      if (item.items && item.items.length > 0) {
        bookmark.children = await Promise.all(
          item.items.map(child => processItem(child, level + 1))
        );
      }
      
      return bookmark;
    };
    
    return Promise.all(outline.map(item => processItem(item)));
  };

  const performSearch = useCallback(async (text) => {
    if (!pdfDocument || !text.trim()) {
      setSearchResults([]);
      return;
    }
    
    setSearching(true);
    const results = [];
    
    try {
      // Search through all pages
      for (let pageNum = 1; pageNum <= numPages; pageNum++) {
        const page = await pdfDocument.getPage(pageNum);
        const textContent = await page.getTextContent();
        
        const pageTextItems = textContent.items
          .filter(item => item.str)
          .map(item => item.str)
          .join(' ');
        
        // Cache page text for future searches
        setPageText(prev => new Map(prev.set(pageNum, pageTextItems)));
        
        // Simple case-insensitive search
        const regex = new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
        let match;
        let matchIndex = 0;
        
        while ((match = regex.exec(pageTextItems)) !== null) {
          results.push({
            pageNumber: pageNum,
            text: match[0],
            index: match.index,
            context: pageTextItems.substring(
              Math.max(0, match.index - 50),
              Math.min(pageTextItems.length, match.index + match[0].length + 50)
            ),
            id: `search_${pageNum}_${matchIndex++}`
          });
        }
      }
      
      setSearchResults(results);
      setCurrentSearchResult(0);
      
      if (results.length === 0) {
        setSnackbar({
          open: true,
          message: `No results found for "${text}"`,
          severity: 'info'
        });
      } else {
        // Navigate to first result
        setPageNumber(results[0].pageNumber);
        setSnackbar({
          open: true,
          message: `Found ${results.length} result${results.length !== 1 ? 's' : ''}`,
          severity: 'success'
        });
      }
    } catch (err) {
      console.error('Search error:', err);
      setSnackbar({
        open: true,
        message: 'Search failed',
        severity: 'error'
      });
    } finally {
      setSearching(false);
    }
  }, [pdfDocument, numPages]);

  const handleSearch = (text) => {
    setSearchText(text);
    
    // Debounce search
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    
    searchTimeoutRef.current = setTimeout(() => {
      performSearch(text);
    }, 500);
  };

  const navigateToSearchResult = (index) => {
    if (searchResults[index]) {
      setCurrentSearchResult(index);
      navigateToPage(searchResults[index].pageNumber);
    }
  };

  const handleBookmarkClick = (bookmark) => {
    if (bookmark.pageNumber) {
      navigateToPage(bookmark.pageNumber);
      setSnackbar({
        open: true,
        message: `Navigated to page ${bookmark.pageNumber}`,
        severity: 'success'
      });
    }
  };

  const toggleBookmarkExpansion = (bookmarkId) => {
    setExpandedBookmarks(prev => {
      const newSet = new Set(prev);
      if (newSet.has(bookmarkId)) {
        newSet.delete(bookmarkId);
      } else {
        newSet.add(bookmarkId);
      }
      return newSet;
    });
  };

  const handleZoomChange = (event, newValue) => {
    setScale(newValue / 100);
  };

  const setZoomMode = (mode) => {
    setViewMode(mode);
    // Auto-calculate scale based on mode
    if (mode === 'fitWidth') {
      setScale(1.0); // This would need container width calculation
    } else if (mode === 'fitPage') {
      setScale(0.8); // This would need container height calculation
    } else if (mode === 'actualSize') {
      setScale(1.0);
    }
  };

  const navigateToPage = (pageNum) => {
    const newPageNum = Math.max(1, Math.min(numPages, pageNum));
    setPageNumber(newPageNum);
    
    // Scroll to the page
    setTimeout(() => {
      const pageElement = document.getElementById(`page-${newPageNum}`);
      const container = scrollContainerRef.current;
      
      if (pageElement && container) {
        // Set navigation flag to prevent scroll listener interference
        container._isNavigating = true;
        
        const containerRect = container.getBoundingClientRect();
        const pageRect = pageElement.getBoundingClientRect();
        
        // Calculate scroll position to center the page
        const scrollTop = container.scrollTop + pageRect.top - containerRect.top - (containerRect.height / 2) + (pageRect.height / 2);
        
        container.scrollTo({
          top: Math.max(0, scrollTop),
          behavior: 'smooth'
        });
        
        // Clear navigation flag after scroll completes
        setTimeout(() => {
          if (container._isNavigating) {
            container._isNavigating = false;
          }
        }, 1000);
      }
    }, 100); // Small delay to ensure page is rendered
  };


  const onDocumentLoadError = (error) => {
    console.error('PDF load error:', error);
    setSnackbar({
      open: true,
      message: 'Failed to load PDF for viewing. Document metadata is still available.',
      severity: 'error'
    });
  };

  const toggleChat = () => {
    if (!chatReadiness?.chat_ready) {
      setSnackbar({
        open: true,
        message: 'Chat is not available for this document. Vector store may be disabled.',
        severity: 'warning'
      });
      return;
    }
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

  const handleSourceClick = useCallback((pageNumber, searchText) => {
    console.log('handleSourceClick called with:', { pageNumber, searchText, type: typeof pageNumber });
    
    if (pageNumber && typeof pageNumber === 'number' && pageNumber > 0) {
      navigateToPage(pageNumber);
      
      // If search text is provided, highlight it
      if (searchText) {
        handleSearch(searchText);
      }
      
      setSnackbar({
        open: true,
        message: `Navigated to page ${pageNumber}`,
        severity: 'success'
      });
    } else {
      console.warn('Invalid page number received:', pageNumber);
      setSnackbar({
        open: true,
        message: 'Unable to navigate: invalid page number',
        severity: 'warning'
      });
    }
  }, []);

  const renderBookmarkItem = (bookmark, index) => {
    const hasChildren = bookmark.children && bookmark.children.length > 0;
    const isExpanded = expandedBookmarks.has(bookmark.id);
    
    return (
      <React.Fragment key={bookmark.id}>
        <ListItem disablePadding>
          <ListItemButton
            onClick={() => handleBookmarkClick(bookmark)}
            sx={{ 
              pl: 2 + bookmark.level * 2,
              py: 0.5,
              '&:hover': {
                bgcolor: 'action.hover'
              }
            }}
          >
            {hasChildren && (
              <ListItemIcon
                sx={{ minWidth: 24 }}
                onClick={(e) => {
                  e.stopPropagation();
                  toggleBookmarkExpansion(bookmark.id);
                }}
              >
                {isExpanded ? <ExpandLess /> : <ExpandMore />}
              </ListItemIcon>
            )}
            <ListItemText
              primary={
                <Typography 
                  variant="body2" 
                  sx={{ 
                    fontSize: Math.max(11, 14 - bookmark.level),
                    fontWeight: bookmark.level === 0 ? 500 : 400
                  }}
                >
                  {bookmark.title}
                </Typography>
              }
              secondary={
                bookmark.pageNumber && (
                  <Typography variant="caption" color="text.secondary">
                    Page {bookmark.pageNumber}
                  </Typography>
                )
              }
            />
          </ListItemButton>
        </ListItem>
        
        {hasChildren && (
          <Collapse in={isExpanded} timeout="auto" unmountOnExit>
            {bookmark.children.map((child, childIndex) => 
              renderBookmarkItem(child, childIndex)
            )}
          </Collapse>
        )}
      </React.Fragment>
    );
  };

  const getChatDrawerWidth = () => {
    if (chatPosition === 'bottom') return '100%';
    return isMobile ? '100%' : 400;
  };

  const getChatDrawerHeight = () => {
    if (chatPosition === 'bottom') return isMobile ? '50%' : '40%';
    return '100%';
  };

  const handleRefreshDocument = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const docInfo = await apiService.getDocumentInfo(documentId);
      setDocument(docInfo);
      
      const chatReady = await apiService.checkDocumentChatReady(documentId);
      setChatReadiness(chatReady);
      
      setSnackbar({
        open: true,
        message: 'Document refreshed successfully',
        severity: 'success'
      });
    } catch (err) {
      setError('Failed to refresh document: ' + err.message);
    } finally {
      setLoading(false);
    }
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
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
        <Button onClick={handleRefreshDocument} startIcon={<Refresh />}>
          Retry
        </Button>
      </Container>
    );
  }

  return (
    <Box ref={containerRef} sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
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
            </Box>
          </Box>

          {/* PDF Controls */}
          {documentFile && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {/* Page Navigation */}
              <IconButton size="small" onClick={() => navigateToPage(1)} disabled={pageNumber <= 1}>
                <FirstPage />
              </IconButton>
              <IconButton size="small" onClick={() => navigateToPage(pageNumber - 1)} disabled={pageNumber <= 1}>
                <NavigateBefore />
              </IconButton>
              
              <Typography variant="body2" sx={{ mx: 1, minWidth: 80, textAlign: 'center' }}>
                {pageNumber} of {numPages}
              </Typography>
              
              <IconButton size="small" onClick={() => navigateToPage(pageNumber + 1)} disabled={pageNumber >= numPages}>
                <NavigateNext />
              </IconButton>
              <IconButton size="small" onClick={() => navigateToPage(numPages)} disabled={pageNumber >= numPages}>
                <LastPage />
              </IconButton>

              <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />

              {/* Zoom Controls */}
              <IconButton size="small" onClick={() => setScale(scale - 0.1)} disabled={scale <= 0.5}>
                <ZoomOut />
              </IconButton>
              
              <Box sx={{ width: 80, mx: 1 }}>
                <Slider
                  value={scale * 100}
                  onChange={handleZoomChange}
                  min={50}
                  max={200}
                  size="small"
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </Box>
              
              <IconButton size="small" onClick={() => setScale(scale + 0.1)} disabled={scale >= 2.0}>
                <ZoomIn />
              </IconButton>

              <FormControl size="small" sx={{ minWidth: 100 }}>
                <Select
                  value={viewMode}
                  onChange={(e) => setZoomMode(e.target.value)}
                  variant="outlined"
                >
                  <MenuItem value="fitWidth">Fit Width</MenuItem>
                  <MenuItem value="fitPage">Fit Page</MenuItem>
                  <MenuItem value="actualSize">Actual Size</MenuItem>
                </Select>
              </FormControl>

              <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />
            </Box>
          )}

          {/* Action Buttons */}
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Tooltip title="Toggle bookmarks">
              <IconButton 
                onClick={() => setBookmarksOpen(!bookmarksOpen)} 
                color={bookmarksOpen ? 'primary' : 'default'}
              >
                <Badge badgeContent={bookmarks.length} color="secondary" max={99}>
                  <Bookmark />
                </Badge>
              </IconButton>
            </Tooltip>
            <IconButton onClick={handleRefreshDocument} title="Refresh document">
              <Refresh />
            </IconButton>
            <IconButton onClick={toggleChatPosition} title="Toggle chat position">
              {chatPosition === 'right' ? <SwapVert /> : <SwapHoriz />}
            </IconButton>
            <IconButton onClick={toggleFullscreen} title="Toggle fullscreen">
              {isFullscreen ? <FullscreenExit /> : <Fullscreen />}
            </IconButton>
          </Box>
        </Toolbar>
      </AppBar>

      {/* Search Bar */}
      {documentFile && (
        <Paper elevation={0} sx={{ borderBottom: 1, borderColor: 'divider', p: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TextField
              size="small"
              placeholder="Search in document..."
              value={searchText}
              onChange={(e) => handleSearch(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    {searching ? <CircularProgress size={16} /> : <Search />}
                  </InputAdornment>
                ),
                endAdornment: searchText && (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => handleSearch('')}>
                      <Clear />
                    </IconButton>
                  </InputAdornment>
                )
              }}
              sx={{ flexGrow: 1, maxWidth: 400 }}
            />
            
            {searchResults.length > 0 && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  {currentSearchResult + 1} of {searchResults.length}
                </Typography>
                <IconButton 
                  size="small" 
                  onClick={() => navigateToSearchResult(Math.max(0, currentSearchResult - 1))}
                  disabled={currentSearchResult <= 0}
                >
                  <NavigateBefore />
                </IconButton>
                <IconButton 
                  size="small" 
                  onClick={() => navigateToSearchResult(Math.min(searchResults.length - 1, currentSearchResult + 1))}
                  disabled={currentSearchResult >= searchResults.length - 1}
                >
                  <NavigateNext />
                </IconButton>
              </Box>
            )}
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
        {/* Bookmarks Sidebar */}
        {bookmarksOpen && (
          <Box
            sx={{
              width: 280,
              flexShrink: 0,
              borderRight: 1,
              borderColor: 'divider',
              bgcolor: 'background.paper',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column'
            }}
          >
            <Box sx={{ 
              p: 2, 
              borderBottom: 1, 
              borderColor: 'divider',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center' }}>
                <Bookmark sx={{ mr: 1 }} />
                Bookmarks
              </Typography>
              <IconButton size="small" onClick={() => setBookmarksOpen(false)}>
                <Close />
              </IconButton>
            </Box>

            <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
              {bookmarks.length === 0 ? (
                <Box sx={{ p: 2, textAlign: 'center' }}>
                  <Typography variant="body2" color="text.secondary">
                    No bookmarks found in this document
                  </Typography>
                </Box>
              ) : (
                <List dense>
                  {bookmarks.map((bookmark, index) => renderBookmarkItem(bookmark, index))}
                </List>
              )}
            </Box>
          </Box>
        )}

        {/* PDF Viewer */}
        <Box 
          sx={{ 
            flexGrow: 1,
            overflow: 'auto',
            bgcolor: '#f5f5f5',
            position: 'relative',
            height: chatPosition === 'bottom' && chatOpen ? 'calc(100% - 40%)' : '100%',
          }}
        >
          {documentFile ? (
            <Box sx={{ 
              p: 2, 
              display: 'flex', 
              flexDirection: 'column',
              alignItems: 'center',
              minHeight: '100%'
            }}>
              {/* Render all pages for scrolling */}
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
                error={
                  <Box sx={{ textAlign: 'center', p: 4 }}>
                    <Alert severity="warning">
                      PDF could not be displayed. The file may not be accessible or there may be a network issue.
                    </Alert>
                  </Box>
                }
              >
                {/* Render all pages for scrolling experience */}
                {Array.from(new Array(numPages), (el, index) => (
                  <Box
                    key={`page_${index + 1}`}
                    id={`page-${index + 1}`}
                    sx={{
                      mb: 2,
                      border: pageNumber === index + 1 ? 2 : 1,
                      borderColor: pageNumber === index + 1 ? 'primary.main' : 'grey.300',
                      borderRadius: 1,
                      overflow: 'hidden',
                      boxShadow: pageNumber === index + 1 ? 3 : 1,
                      transition: 'border-color 0.3s ease, box-shadow 0.3s ease'
                    }}
                  >
                    <Page
                      pageNumber={index + 1}
                      scale={scale}
                      renderTextLayer={true}
                      renderAnnotationLayer={true}
                      onLoadSuccess={(page) => {
                        pageRefs.current.set(index + 1, page);
                      }}
                      onClick={() => setPageNumber(index + 1)}
                      loading={
                        <Box sx={{ 
                          height: 800, 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'center',
                          bgcolor: 'grey.100'
                        }}>
                          <CircularProgress size={24} />
                        </Box>
                      }
                    />
                    {/* Page number overlay */}
                    <Box
                      sx={{
                        position: 'absolute',
                        top: 8,
                        right: 8,
                        bgcolor: 'rgba(0, 0, 0, 0.7)',
                        color: 'white',
                        px: 1,
                        py: 0.5,
                        borderRadius: 1,
                        fontSize: '0.75rem',
                        fontWeight: 'bold'
                      }}
                    >
                      {index + 1}
                    </Box>
                  </Box>
                ))}
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
              <Typography variant="body1" sx={{ mb: 1 }}>
                Document: {document?.filename}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Pages: {document?.total_pages || 'Unknown'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Status: {document?.status}
              </Typography>
              
              {document?.status === 'completed' && (
                <Alert severity="info" sx={{ mt: 2, maxWidth: 400 }}>
                  Document is processed but PDF viewing is not available. 
                  This could be due to file access permissions or the file serving endpoint not being configured.
                </Alert>
              )}
              
              {document?.status !== 'completed' && (
                <Alert severity="warning" sx={{ mt: 2, maxWidth: 400 }}>
                  Document is still being processed. PDF viewing will be available once processing is complete.
                </Alert>
              )}
            </Box>
          )}
        </Box>

        {/* Chat Interface */}
        {chatReadiness?.chat_ready && (
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
          </Drawer>
        )}
      </Box>

      {/* Floating Action Buttons */}
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
            message: chatReadiness?.message || 'Chat functionality is not available for this document',
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
